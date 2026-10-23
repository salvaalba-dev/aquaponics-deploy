"""Synthetic cleanup regressions: no Drive, credentials, or real recordings."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cleanup", Path(__file__).with_name("cotejo.py")
)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.recording = self.root / "project-sync_2026-01-02-03-04-05.mp4"
        self.recording.write_bytes(b"synthetic recording")
        self.deliveries = self.root / "entregas"
        self.delivery = self.deliveries / ("2026-01-02_" + self.recording.stem)
        self.delivery.mkdir(parents=True)
        self.metadata = self.delivery / "meta.json"
        self.document = {
            "room": self.recording.stem,
            "department": "project",
            "aviso": "recipient@example.invalid",
            "bandeja_id": "inbox",
        }
        self.save(self.document)
        for suffix in (".txt", ".resumen.md", ".acta.pdf", ".coherencia.md"):
            path = self.root / ("project-sync" + suffix)
            path.write_bytes(("synthetic " + suffix).encode())
            (self.delivery / path.name).write_bytes(path.read_bytes())
        cleanup.confirm_delivery(self.metadata, self.recording)
        self.routes = {"project": "project-archive"}
        self.remote = [
            {
                "id": "synthetic-" + str(i),
                "size": entry["size"],
                "md5Checksum": entry["md5"],
                "parents": ["project-archive"],
            }
            for i, entry in enumerate(
                cleanup.read_metadata(self.metadata)["delivery"]["files"]
            )
        ]

    def save(self, document):
        self.metadata.write_text(json.dumps(document), encoding="utf-8")

    def request(self, params):
        self.assertIn("'project-archive' in parents", params["q"])
        return {"files": self.remote}

    def plan(self, request=None):
        return cleanup.cleanup_plan(
            self.recording, self.deliveries, self.routes, request or self.request
        )

    def test_complete_group_can_be_verified_without_deletion(self):
        plan = self.plan()
        self.assertEqual(len(plan), 5)
        self.assertTrue(all(path.exists() for path, _ in plan))

    def test_repeated_room_recordings_hold_shared_local_derivatives(self):
        other = self.root / "project-sync_2026-01-03-03-04-05.mp4"
        other.write_bytes(b"another recording with shared derivative names")
        with self.assertRaisesRegex(cleanup.Pending, "shared-local-derivatives"):
            self.plan()

    def test_missing_delivery_copy_prevents_confirmation(self):
        (self.delivery / "project-sync.txt").unlink()
        self.save(self.document)
        with self.assertRaises(OSError):
            cleanup.confirm_delivery(self.metadata, self.recording)
        self.assertNotIn("delivery", cleanup.read_metadata(self.metadata))

    def test_explicit_delete_removes_only_verified_artifacts(self):
        control = Path(str(self.recording) + ".dept")
        control.write_text("project", encoding="utf-8")
        unrelated = self.root / "other.mp4"
        unrelated.write_bytes(b"unrelated")
        cleanup.remove_verified(self.plan())
        self.assertFalse(self.recording.exists())
        self.assertTrue(self.metadata.exists())
        self.assertTrue((self.delivery / "project-sync.txt").exists())
        self.assertTrue(control.exists())
        self.assertTrue(unrelated.exists())

    def test_video_alone_does_not_prove_derivatives_are_archived(self):
        self.remote = self.remote[:1]
        with self.assertRaisesRegex(cleanup.Pending, "artifact-not-in-final-archive"):
            self.plan()
        self.assertTrue(self.recording.exists())

    def test_same_bytes_in_another_project_do_not_count(self):
        for item in self.remote:
            item["parents"] = ["another-archive"]
        with self.assertRaisesRegex(cleanup.Pending, "artifact-not-in-final-archive"):
            self.plan()

    def test_mail_address_or_inbox_is_not_delivery_proof(self):
        self.save(self.document)
        with self.assertRaisesRegex(cleanup.Pending, "delivery-not-confirmed"):
            self.plan()

    def test_missing_explicit_route_holds_instead_of_falling_back(self):
        self.routes = {"organization": "organization-archive"}
        with self.assertRaisesRegex(cleanup.Pending, "explicit-final-archive-required"):
            self.plan()

    def test_substring_and_duplicate_delivery_directories_are_rejected(self):
        self.delivery.rename(self.delivery.with_name(self.delivery.name + "-other"))
        with self.assertRaisesRegex(cleanup.Pending, "delivery-missing-or-ambiguous"):
            self.plan()
        self.delivery.mkdir()
        self.save(self.document)
        (self.deliveries / ("2026-01-03_" + self.recording.stem)).mkdir()
        with self.assertRaisesRegex(cleanup.Pending, "delivery-missing-or-ambiguous"):
            self.plan()

    def test_wrong_meeting_metadata_is_rejected(self):
        document = cleanup.read_metadata(self.metadata)
        document["room"] = "other"
        self.save(document)
        with self.assertRaisesRegex(cleanup.Pending, "meeting-mismatch"):
            self.plan()

    def test_changed_local_or_delivered_content_is_rejected(self):
        path = self.root / "project-sync.txt"
        path.write_bytes(b"new content")
        with self.assertRaisesRegex(cleanup.Pending, "delivery-content-changed"):
            self.plan()
        path.write_bytes(b"synthetic .txt")
        (self.delivery / path.name).write_bytes(b"different delivered bytes")
        with self.assertRaisesRegex(cleanup.Pending, "delivery-copy-mismatch"):
            self.plan()

    def test_new_derivative_after_delivery_is_not_silently_deleted(self):
        (self.root / "project-sync.resumen.pdf").write_bytes(b"new PDF")
        with self.assertRaisesRegex(cleanup.Pending, "delivery-content-changed"):
            self.plan()

    def test_size_mismatch_is_rejected_even_with_matching_hash(self):
        self.remote[0]["size"] += 1
        with self.assertRaisesRegex(cleanup.Pending, "artifact-not-in-final-archive"):
            self.plan()

    def test_all_pages_are_required_before_cleanup(self):
        calls = []

        def request(params):
            calls.append(params)
            if "pageToken" not in params:
                return {"files": self.remote[:1], "nextPageToken": "next"}
            self.assertEqual(params["pageToken"], "next")
            return {"files": self.remote[1:]}

        self.assertEqual(len(self.plan(request)), 5)
        self.assertEqual(len(calls), 2)

    def test_failed_or_incomplete_page_never_authorizes_cleanup(self):
        def unavailable(params):
            raise OSError("synthetic transport failure")

        with self.assertRaises(OSError):
            self.plan(unavailable)
        with self.assertRaisesRegex(cleanup.Pending, "incomplete-archive-listing"):
            self.plan(lambda params: {"files": self.remote, "incompleteSearch": True})
        self.assertTrue(self.recording.exists())

    def test_pagination_cycle_is_rejected(self):
        with self.assertRaisesRegex(cleanup.Pending, "invalid-pagination"):
            self.plan(lambda params: {"files": self.remote, "nextPageToken": "loop"})

    def test_recheck_before_unlink_preserves_whole_group_on_change(self):
        plan = self.plan()
        plan[-1][0].write_bytes(b"changed after planning")
        with self.assertRaisesRegex(
            cleanup.Pending, "local-file-changed-before-cleanup"
        ):
            cleanup.remove_verified(plan)
        self.assertTrue(all(path.exists() for path, _ in plan))

    def test_duplicate_metadata_keys_and_route_keys_are_rejected(self):
        self.metadata.write_text('{"room":"one","room":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(cleanup.Pending, "duplicate-metadata-field"):
            self.plan()
        with self.assertRaisesRegex(cleanup.Pending, "invalid-archive-route-map"):
            cleanup.archive_routes("project:one\nproject:two")

    def test_processor_and_scheduler_have_no_immediate_delete_bypass(self):
        shell = Path(__file__).with_name("post-meeting.sh").read_text(encoding="utf-8")
        processor_path = Path(__file__).with_name("process_recording.py")
        if not processor_path.exists():
            processor_path = (
                Path(__file__).parent.parent
                / "whisper-transcribe"
                / "process_recording.py"
            )
        processor = processor_path.read_text(encoding="utf-8")
        self.assertNotIn('rm -f "$f"', shell)
        self.assertNotIn("os.remove(path)", processor)
        self.assertIn('"$delivery_status" = "0"', shell)
        self.assertIn('"${TEST_NO_UPLOAD:-0}" != "1"', shell)
        self.assertIn("--confirm-delivery", shell)


if __name__ == "__main__":
    unittest.main()
