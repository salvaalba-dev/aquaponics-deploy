# AU binding for the generic service-start controller

Status: review only, **not deployable as a standalone pilot**. No VPS changes.

## Product and installation boundary

Reusable code, tests and unit rendering live in the public fork:
https://github.com/salvaalba-dev/phantomyard-tools/tree/6c8fc1dbfb863247466f0f38797e0c32529a6f00/persona-service-control

AU references that exact commit. It does not maintain a renamed copy of the
controller. The previous Alma-specific Python scripts and unit files, together
with the limited sudo mitigation, are superseded and removed from this branch.
They were never installed during this work. Git history retains the evidence.

The candidate AU binding is alma-browser.binding.json:

```json
{
  "version": 1,
  "id": "alma-browser",
  "account": "pb-alma",
  "uid": 1059,
  "unit": "chrome-alma.service"
}
```

Alma belongs in this deployment mapping, not in executable filenames. New
installations can use the same controller with their own root-managed bindings.
The binding ID derives the socket and unit names; requesters cannot select an
arbitrary service. Root must review mappings against the approved PhantomOrg
service policy before enabling them. Automatic policy-to-runtime binding is not
implemented; this binding is not evidence of such validation or query approval.

## Eventual mapping, subject to complete pilot approval

| Source | Eventual path |
|---|---|
| Product persona_service_control.py at pinned commit | /usr/local/libexec/persona_service_control.py |
| AU alma-browser.binding.json | /etc/persona-service-control/alma-browser.json |
| Renderer output | /etc/systemd/system/persona-service-start-alma-browser.socket and persona-service-start-alma-browser@.service |

The nonsecret binding should be root-owned 0644 with root-owned, nonwritable
parents so the contained client can read it. The product rejects symlinks,
untrusted ownership, writable parents and UID drift. Root owns code and units.
Read-only inventory confirms primary GID 1059, which must be rechecked before
application. The account's actual primary GID is resolved on the target; the
renderer uses that numeric GID, without assuming that group and account names or
UID and GID match. AU CI uses a synthetic GID and is not host attestation.

The new control socket is /run/persona-service-control/alma-browser.sock. This is
distinct from Chrome's CDP endpoint. The product client requests only a fixed
start and needs no sudo. Its handler checks kernel peer UID and preserves
NoNewPrivileges. STARTED means only systemctl returned zero, not browser health,
Google login, NotebookLM availability, query approval or isolation.

## Integration still pending

The actual tools/notebooklm-web.js wakeAndCheck path must replace its sudo call
with this fixed argv, retaining its own post-start browser check:

```text
/usr/bin/python3 -I /usr/local/libexec/persona_service_control.py client --config /etc/persona-service-control/alma-browser.json
```

CLIENT-INTEGRATION.md now supplies the exact wake-function patch and source
preflight. That patch is tested but unapplied, and is not a complete pilot.
Require the existing mapping to be exactly chrome-alma and CDP 18802 before
selecting this AU binding. Do not redirect another persona to Alma. Keep real
clients and Chrome together in Alma's eventual network namespace. The old direct
client, real shell wrapper, timers and idle observer all need reconciled coverage.
The idle observer must inspect that namespace and coordinate with active queries.
Do not weaken NoNewPrivileges or copy, replace or reauthenticate the browser profile.

Retire the existing unrestricted helper and sudoers grant only in the complete
approved transition after actual hardened-path validation. No existing host file
has been removed. Per-query approval remains Paco OR Salvador through AU
Coordination; browser start permission does not implement or replace it.

Still required: full dependency coverage, namespace/DNS/NAT and firewall diff,
complete rollback, host unit verification, explicit application approval, real
own-tool operation, bidirectional cross-identity denial for two pairs and
persistence checks. None is established by the controller's CI tests.
