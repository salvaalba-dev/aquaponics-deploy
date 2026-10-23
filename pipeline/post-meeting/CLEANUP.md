# Verified local recording cleanup

The processor retains local originals after uploading to intake, including when
called without `--keep`. `CLEANUP_AFTER_DELIVERY=1` no longer bypasses final
archive verification. The scheduled checker is the sole local deletion path.

## Evidence required

- Exactly one dated delivery directory matching the complete recording stem.
- Its existing `meta.json` binds the exact recording and explicit department.
- Before generating MIME, record the artifact fingerprints in the existing
  metadata and invalidate any older delivery acceptance. Validate the rendered
  attachments against that preparation, then submit the exact in-memory MIME
  bytes to sendmail. Record their SHA-256 only after acceptance and another
  artifact check. Changes before or during submission leave cleanup held.
  This proves local MTA acceptance, not that the recipient read the message.
  The coherence report has its separate notification and is not an attachment
  of the main message; its own final archive proof is still required.
- Every candidate's name, byte size, and Drive-compatible MD5 still match the
  recorded delivery. Derivative copies in the delivery directory also match.
- Every candidate, including each PDF and the coherence report if present, is
  found with the same size and checksum in the explicitly configured final
  destination. The video alone never authorizes deleting its derivatives.
- Each candidate consumes a distinct Drive object ID. Identical contents need
  separate objects; repeated entries for one ID do not increase its count.
- Every page of the destination listing must succeed. Incomplete searches,
  inaccessible destinations, ambiguous metadata, and changed files retain
  the entire group. A second local-content check precedes deletion.

The command defaults to reporting only. `--borrar` first renames the verified
artifacts into a private temporary directory on the same filesystem, with a
durable journal. Failures before commitment restore moved files without
overwriting newly created sources. Only after verifying the whole staged group
is the transaction marked committed and its contents purged. Startup recovery
restores interrupted preparations or resumes committed purges before new scans.
An interrupted purge may leave staged leftovers; multi-file deletion is not
atomic. Such leftovers remain journaled for retry instead of leaving an
unrecorded partially deleted group. No permanent document backup is introduced.

Delivery copies, control metadata, other recordings, and Drive objects remain
intact. This does not certify native PhantomDocs registration or alter any
document category, owner, ACL, archive record, or history.

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

The scheduler defaults to `CLEANUP_MODE=report`, including when the variable is
unset or empty. It invokes the checker without `--borrar`, so neither deletion
nor journal recovery is performed. An unrecognized mode holds the checker
without invoking it. After reviewing the reports and reconciling historical
deliveries, an operator can explicitly set `CLEANUP_MODE=delete` to request
verified cleanup. This does not bypass any delivery or final archive checks.

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
