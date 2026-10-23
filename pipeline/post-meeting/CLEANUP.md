# Verified local recording cleanup

The processor retains local originals after uploading to intake, including when
called without `--keep`. `CLEANUP_AFTER_DELIVERY=1` no longer bypasses final
archive verification. The scheduled checker is the sole local deletion path.

## Evidence required

- Exactly one dated delivery directory matching the complete recording stem.
- Its existing `meta.json` binds the exact recording and explicit department.
- A delivery record is added to that metadata only after sendmail accepts a
  non-test delivery. This proves acceptance by the local mail system, not that
  the recipient read the message. Merely naming a recipient or inbox proves
  nothing. No new notification, upload, or duplicate ingestion is performed.
- Every candidate's name, byte size, and Drive-compatible MD5 still match the
  recorded delivery. Derivative copies in the delivery directory also match.
- Every candidate, including each PDF and the coherence report if present, is
  found with the same size and checksum in the explicitly configured final
  destination. The video alone never authorizes deleting its derivatives.
- Every page of the destination listing must succeed. Incomplete searches,
  inaccessible destinations, ambiguous metadata, and changed files retain
  the entire group. A second local-content check precedes deletion.

The command defaults to reporting only. `--borrar` removes only the verified
artifact list; delivery copies, control metadata, other recordings, and Drive
objects remain intact. It does not certify native PhantomDocs registration or
alter any document category, owner, ACL, archive record, or history.

## Explicit final destinations

Add `CLEANUP_ARCHIVE_MAP` to the existing deployment configuration as newline
separated `department:final-folder-id` pairs. Reuse approved final destinations
from the existing custody policy; do not use intake folders. For example:

```bash
CLEANUP_ARCHIVE_MAP='organization:synthetic-organization-archive
project:synthetic-project-archive'
```

No route is inferred from a title or from another department. Missing mappings
hold cleanup. Historical metadata without a real delivery record also holds
cleanup: do not invent receipts or re-upload files to make it pass. Reconcile
those recordings separately against their actual delivery and archive evidence.

The checker uses the existing service account with a read-only Drive scope.
No new dependencies or services are introduced. Production must retain its
existing post-meeting round lock, and recording producers must be quiescent
before cleanup. This is a trusted local deployment process, not a sandbox
against another process concurrently replacing files or moving Drive objects.

## Rollout

Review live/source differences before installing; repository snapshots can lag
the host. Install the checker and scheduler together, configure only approved
routes, and run reporting mode before enabling deletion. Keep old recordings
held until independently reconciled. Installing this patch is a separate step
from approving its PR; these tests never contact Drive or touch production.

```bash
python3 -m unittest discover -s pipeline/post-meeting -p 'test_*.py' -v
bash -n pipeline/post-meeting/post-meeting.sh
python3 -m compileall -q pipeline/post-meeting pipeline/whisper-transcribe/process_recording.py
```
