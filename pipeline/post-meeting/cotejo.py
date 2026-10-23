#!/usr/bin/env python3
"""Verify each local artifact in its explicit final archive before cleanup."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

REC = Path("/var/recordings")
SA_PATH = "/opt/whisper-transcribe/google-service-account.json"
SUBJECT = "secretaria@aquaponicsunited.com"
SUFFIXES = (
    ".txt",
    ".resumen.md",
    ".acta.pdf",
    ".resumen.pdf",
    ".transcripcion.pdf",
    ".coherencia.md",
)


class Pending(ValueError):
    """Evidence is incomplete; retain every local artifact in the group."""


def room_name(recording):
    return re.sub(r"_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$", "", recording.stem)


def regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise Pending("non-regular-local-file")
    return info


def fingerprint(path):
    before = regular(path)

    def identity(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    digest = hashlib.md5()  # Drive's binary-file integrity field, not authentication.
    with path.open("rb") as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise Pending("local-file-changed")
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    after = regular(path)
    if identity(before) != identity(after):
        raise Pending("local-file-changed")
    return {"name": path.name, "size": after.st_size, "md5": digest.hexdigest()}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Pending("duplicate-metadata-field")
        result[key] = value
    return result


def read_metadata(path):
    regular(path)
    with path.open("rb") as source:
        data = source.read((1 << 20) + 1)
    if len(data) > 1 << 20:
        raise Pending("metadata-too-large")
    result = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(result, dict):
        raise Pending("invalid-metadata")
    return result


def artifacts(recording):
    root = recording.parent
    candidates = [recording]
    for suffix in SUFFIXES:
        path = root / (room_name(recording) + suffix)
        if path.exists() or path.is_symlink():
            regular(path)
            candidates.append(path)
    names = {p.name for p in candidates}
    required = {room_name(recording) + suffix for suffix in (".txt", ".resumen.md")}
    if not required <= names:
        raise Pending("processing-incomplete")
    return candidates


def validate_binding(metadata, recording):
    if metadata.get("room") != recording.stem:
        raise Pending("meeting-mismatch")
    department = metadata.get("department")
    if not isinstance(department, str) or not re.fullmatch(
        r"[a-z][a-z0-9_-]{0,63}", department
    ):
        raise Pending("invalid-department")
    return department


def confirm_delivery(metadata_path, recording):
    """Called only after sendmail accepts the real, uploaded delivery.

    This records local MTA acceptance, not final recipient receipt or archival.
    Extend the existing delivery metadata rather than creating a second registry.
    """
    metadata = read_metadata(metadata_path)
    validate_binding(metadata, recording)
    if metadata_path.parent.is_symlink():
        raise Pending("symlink-delivery-directory")
    files = [fingerprint(path) for path in artifacts(recording)]
    for entry in files[1:]:
        if fingerprint(metadata_path.parent / entry["name"]) != entry:
            raise Pending("delivery-copy-mismatch")
    metadata["delivery"] = {
        "schema": 1,
        "status": "sendmail-accepted",
        "recording": recording.name,
        "files": files,
    }
    fd, temporary = tempfile.mkstemp(prefix=".meta-", dir=metadata_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(metadata, output, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, metadata_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def archive_routes(value):
    """Read explicit deployment routes; no fallback from project to organization."""
    routes = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        department, separator, folder = line.strip().partition(":")
        if (
            not separator
            or department in routes
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", department)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", folder)
        ):
            raise Pending("invalid-archive-route-map")
        routes[department] = folder
    return routes


def drive_reader():
    # Import and authenticate only for a live archive scan, never on import/tests.
    import google.auth.transport.requests as transport
    import google.oauth2.service_account as service_account

    credentials = service_account.Credentials.from_service_account_file(
        SA_PATH,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
        subject=SUBJECT,
    )
    credentials.refresh(transport.Request())

    def request(params):
        url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
            params
        )
        query = urllib.request.Request(
            url, headers={"Authorization": "Bearer " + credentials.token}
        )
        with urllib.request.urlopen(query, timeout=60) as response:
            return json.load(response)

    return request


def archive_index(folder, request):
    """Require a complete, paginated response from this exact destination."""
    result = set()
    token = None
    seen = set()
    for _ in range(1000):
        params = {
            "q": "'%s' in parents and trashed=false" % folder,
            "fields": "nextPageToken,incompleteSearch,files(id,size,md5Checksum,parents)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if token:
            params["pageToken"] = token
        response = request(params)
        if response.get("incompleteSearch") or not isinstance(
            response.get("files"), list
        ):
            raise Pending("incomplete-archive-listing")
        for item in response["files"]:
            digest = item.get("md5Checksum", "")
            size = item.get("size", "")
            if (
                folder in item.get("parents", [])
                and item.get("id")
                and re.fullmatch(r"[0-9a-f]{32}", digest)
                and str(size).isdigit()
            ):
                result.add((int(size), digest))
        token = response.get("nextPageToken")
        if not token:
            return result
        if not isinstance(token, str) or token in seen:
            raise Pending("invalid-pagination")
        seen.add(token)
    raise Pending("archive-listing-limit")


def cleanup_plan(recording, deliveries, routes, request):
    """Return a complete verified group or raise; never match by substring."""
    if any(
        other != recording and room_name(other) == room_name(recording)
        for other in recording.parent.glob("*.mp4")
    ):
        raise Pending("shared-local-derivatives")
    matches = []
    for directory in deliveries.iterdir():
        # Only this exact recording's dated delivery directory is eligible.
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}_" + re.escape(recording.stem), directory.name
        ):
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise Pending("invalid-delivery-directory")
        matches.append(directory / "meta.json")
    if len(matches) != 1:
        raise Pending("delivery-missing-or-ambiguous")
    metadata = read_metadata(matches[0])
    department = validate_binding(metadata, recording)
    folder = routes.get(department)
    if not folder:
        raise Pending("explicit-final-archive-required")
    receipt = metadata.get("delivery")
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != 1
        or receipt.get("status") != "sendmail-accepted"
        or receipt.get("recording") != recording.name
    ):
        raise Pending("delivery-not-confirmed")
    candidates = artifacts(recording)
    local = [fingerprint(path) for path in candidates]
    if receipt.get("files") != local:
        raise Pending("delivery-content-changed")
    for entry in local[1:]:
        if fingerprint(matches[0].parent / entry["name"]) != entry:
            raise Pending("delivery-copy-mismatch")
    index = archive_index(folder, request)
    if any((entry["size"], entry["md5"]) not in index for entry in local):
        raise Pending("artifact-not-in-final-archive")
    return list(zip(candidates, local))


def remove_verified(plan):
    # Recheck the whole group immediately before the first unlink. The scheduler
    # must hold its existing post-meeting lock and keep producers quiescent.
    for path, expected in plan:
        if fingerprint(path) != expected:
            raise Pending("local-file-changed-before-cleanup")
    for path, expected in plan:
        if fingerprint(path) != expected:
            raise Pending("local-file-changed-before-cleanup")
        path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--borrar", action="store_true", help="remove verified local artifacts"
    )
    parser.add_argument("--confirm-delivery", type=Path)
    parser.add_argument("--recording", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.confirm_delivery:
            if not args.recording or args.borrar:
                raise Pending("invalid-delivery-command")
            confirm_delivery(args.confirm_delivery, args.recording)
            return 0
        routes = archive_routes(os.environ.get("CLEANUP_ARCHIVE_MAP", ""))
        if not routes:
            raise Pending("explicit-final-archive-required")
        request = drive_reader()
    except (OSError, ValueError, UnicodeError):
        print(
            "HOLD cleanup: configuration or delivery evidence unavailable",
            file=sys.stderr,
        )
        return 2
    pending = False
    for recording in sorted(REC.glob("*.mp4")):
        try:
            plan = cleanup_plan(recording, REC / "entregas", routes, request)
            if args.borrar:
                remove_verified(plan)
            print(("REMOVED " if args.borrar else "VERIFIED ") + recording.name)
        except Exception:
            # A transport/parse/file failure cannot authorize deletion or expose
            # credential-bearing response bodies in logs.
            pending = True
            print("HOLD cleanup: " + recording.name + " (incomplete evidence)")
    return 2 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
