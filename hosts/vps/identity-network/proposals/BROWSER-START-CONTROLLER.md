# Fixed browser-start controller proposal

Status: a review component, **not an installation or network isolation plan**.
Do not install these files independently of the complete approved pilot.

## Boundary

The hardened Alma process cannot elevate through sudo. Instead, a system socket
can activate an external root process for one fixed operation. The caller keeps
NoNewPrivileges; the handler also has NoNewPrivileges and an empty capability
set. Root's access to the system manager, rather than caller privilege escalation,
allows it to request the fixed unit start.

The pathname socket is accessible only to root and group pb-alma (0660), inside a
root-owned directory that must not be writable by Alma. The handler independently
checks Linux SO_PEERCRED: only pb-alma's current UID or root is accepted. Unknown
accounts and a target account resolving to UID zero are rejected. Membership in
the socket group alone does not bypass the peer UID check. Root remains an
administrator; this design does not isolate a persona from the host administrator.

The service accepts exactly the seven bytes `ENSURE\n`, followed by write EOF.
No arguments, configuration, credentials, commands, unit names, URLs or ports
are read from the request or caller environment. Requests have a two-second
absolute deadline and a strict byte bound. PID 1 is invoked through a fixed argv,
without a shell or inherited environment, with a 25-second timeout. Subprocess
output is discarded. Each handler has a 35-second runtime limit; the socket limits
concurrent handlers. Peer credentials and request data are not journalled.

The response is `STARTED\n` if the fixed `systemctl start chrome-alma.service`
operation returns zero, otherwise `ERROR\n` (or connection failure). A malformed
authorized request receives `DENIED\n`; an unauthorized peer receives no response.
Active units are not restarted by `systemctl start`. Retrying only requests the
same fixed start operation. A timeout does not prove the system manager cancelled
its start job. The controller never issues stop, restart, kill or network requests.

STARTED is **not** browser health, Google login validation, NotebookLM availability,
query approval or network isolation. The client must check its own browser after
the start. This controller does not enforce the Paco-or-Salvador per-query rule.

## Proposed file mapping

| Repository file | Eventual host path, subject to approval |
|---|---|
| alma_browser_start_broker.py | /usr/local/libexec/alma_browser_start_broker.py |
| alma_browser_start_client.py | /usr/local/libexec/alma_browser_start_client.py |
| phantomorg-alma-browser-start.socket | /etc/systemd/system/phantomorg-alma-browser-start.socket |
| phantomorg-alma-browser-start@.service | /etc/systemd/system/phantomorg-alma-browser-start@.service |

All installed code and units must be root-owned and not writable by any persona.
The scripts are invoked with `/usr/bin/python3 -I`; they need only Python's standard
library. The proposed socket path is `/run/phantomorg/alma-browser-start.sock`.
Before application, check ownership, permissions and symlinks for the entire
existing parent path, unit drift and dependencies. No profiles or credentials are
read, copied or changed by the proposed controller.

The existing tools/notebooklm-web.js wakeAndCheck path must replace its sudo call
with a fixed invocation of `/usr/bin/python3 -I` and the client path above, after
requiring its existing mapping to be exactly chrome-alma and port 18802. Keep the
subsequent browser check in the caller's namespace. Other personas must not be
silently mapped to Alma. No live client patch is included here: the complete
client and observer changes must be reviewed together with namespace placement.

Retire the old sudoers grant only as part of the approved transition after the
new path works under the real hardened execution context. Do not activate this
controller alongside an unreconciled idle observer: the observer still needs to
inspect Alma's namespace and coordinate with active queries. Browser clients,
scheduled tasks and the observer must agree on that lifecycle.

## Verification and remaining work

Tests exercise rejected peers and requests, fragmented frames, absolute deadlines,
fixed subprocess arguments, failures, and a real AF_UNIX exchange from a child
with NoNewPrivs=1. The service operation in tests is always fake: no browser,
system service or authenticated session is accessed. The peer test uses kernel
credentials on Linux; fake credentials also cover unauthorized identities.

CI verifies the proposed unit files with systemd-analyze verify without loading,
enabling or starting them. This is syntax/dependency verification in the CI image,
not host attestation or a complete namespace pilot validation.

Still required before application: all client paths and idle-observer integration,
namespace/NAT/DNS and shared-service dependency diff, complete rollback, host unit
verification, then Salvador's explicit approval. Live acceptance must retain the
profiles in place and test actual tools, bidirectional isolation for two identity
pairs, persistence and rollback. None of these live acceptance checks has run.

Primary references:

- https://github.com/systemd/systemd/blob/v255/man/systemd.socket.xml
- https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml
- https://www.kernel.org/doc/html/latest/userspace-api/no_new_privs.html
