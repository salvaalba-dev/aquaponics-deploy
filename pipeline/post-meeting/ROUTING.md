# Explicit meeting delivery routing

This correction belongs to the existing post-meeting deployment. It adds no
daemon, credentials, document registry, ACL policy or alternative upload path.

## Routing contract

Before processing or uploading a recording, `post-meeting.sh` invokes the adjacent
`resolve-route.py` using its existing processing Python. The resolver selects an
explicit local `.dept` override, otherwise the local `.meta.json` department,
otherwise the existing Drive meeting-order lookup. A present invalid or incomplete
local source is authoritative and blocks delivery rather than falling through.
Missing order context, failed lookup, timeout and invalid department values return
exit 2 and a redacted HOLD reason. The log identifies the affected meeting.

The selected key must have its own email and inbox in the existing deployment
maps. An unknown key never falls back to Secretariat. Folder names, recording
titles, transcript text and the fact that Pepa processes a meeting cannot assign
its destination, category or audience. Pepa may process a project meeting while
the explicit delivery context selects the project inbox. No new context is
inferred from an ALMAPONIA word in a title.

The resolver does not change the current producer contract. New workflow raw
intake and project delivery are separate concepts: the opt-in PhantomDocs workflow
uses Pepa's common raw-recording intake, then an authorized archive handover.
Do not replace the entire department map to activate that workflow.

## Completion and the existing ingestion boundary

The old pipeline README describes PhantomDocs ingestion as both registration and
archival. The reviewed `fix/au-bandeja-ingest` utility only indexes existing Drive
references. It does not move, rename, upload or archive files. Its ALMAPONIA scan
reads the canonical final project archive, not the project intake. Therefore a
successful upload or the legacy `.done` marker is not evidence of registration
or final archival. The new STATE log states those stages are unconfirmed.

This patch prevents incorrect future delivery; it does not activate an archiver
or the newer workflow. Registration and archival require their own verified
native receipts. A historical meeting already uploaded must be reconciled using
its actual Drive IDs and hashes, not processed/uploaded again. Never clear `.done`
or seen markers to force recovery. Retain originals and all existing history.

The companion ingestion correction holds unresolved meeting groups, logs exact
file IDs and continues independent approved groups. Exit 2 means pending review;
it is not a completed ingest. ACL or integrity conflicts remain fatal.

## Validation and deployment

Run from this directory, without Drive credentials or any running service:

```bash
python3 -m unittest test_route -v
bash -n post-meeting.sh
python3 -m compileall -q resolve-route.py test_route.py
```

Review the current installed scripts and configuration against the versioned
source before deployment. Copy only `post-meeting.sh` and `resolve-route.py` to
their corresponding existing paths, preserving a private rollback copy. Use mode
0755 and the current administrator ownership. Do not copy sanitized configuration
over live configuration, overwrite other files, rerun a completed meeting or
restart a persona. Installing these files does not itself invoke processing.

Before enabling another scheduled pass, validate one explicit AU route, one
explicit project route and one missing-context case with synthetic local inputs.
Then observe the existing timer's next approved new meeting: check actual Drive
parent, returned IDs, delivery evidence and subsequent native registration/archive
receipts separately. Do not manufacture completion receipts for earlier meetings.

Pending routing remains in the existing log until its authoritative metadata is
corrected. This change does not add a notification service or claim that the
existing sender automatically performs human Secretariat approval/signature.
