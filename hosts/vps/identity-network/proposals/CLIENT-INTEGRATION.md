# AU browser client integration candidate

Status: tested candidate, **not a complete or deployable namespace pilot**.
No host files, services, profiles, credentials or firewall rules were changed.
No browser tool, authenticated session or cross-identity connection was tested.

## Read-only baseline, 2026-10-15

The actual browser backend is:
/home/pb-alma/.local/share/phantombot/tools/notebooklm-web.js

It is not under personas/alma/tools. That directory holds the real shell wrapper,
notebooklm-web.sh, whose NB_SCRIPT points to the store-level backend above.
Its dispatch branches execute that script directly for session checks, notebook
lists, sources, history and queries. The separate notebooklm.sh/Gemini interface
is not changed or assumed interchangeable.

Verified fingerprints:

| Item | SHA-256 |
|---|---|
| Entire browser backend | 03d181079700b7e955ed14ee57a56bacd811366f61b5ffaf91bce0de5ba2cd49 |
| wakeAndCheck, lines 68–81, including final LF | aa4fa2c289cd15fc8aa0bc45d7ac53b18079dc471f23269dd033f051f6bf658f |
| /usr/local/sbin/chrome-alma-idle.sh | 7f18df7274dfac8e3db703f6fd5e893bb44a5bf1ac1a31bb20e551a410845152 |

Account lookup confirms pb-alma UID 1059 and primary GID 1059. Recheck both at
application time. Chrome's effective unit runs as User=pb-alma, Group=pb-alma,
PrivateNetwork=no, empty NetworkNamespacePath and NoNewPrivileges=no. This last
setting is distinct from Alma's hardened Phantombot process, previously confirmed
with NoNewPrivs=1. Do not report Chrome as already having that flag enabled.

The idle unit invokes chrome-alma-idle.sh chrome-alma 18802 as root (empty User),
with NoNewPrivileges=no, an empty NetworkNamespacePath and the full observed
capability bounding set. These observations are not changes to its hardening.

## Exact client proposal

notebooklm-service-control.patch replaces only wakeAndCheck with the English
function in notebooklm-wake.candidate.js. This is AU-specific adapter wiring;
the reusable controller remains exclusively in the product repository at the
pinned commit documented in BROWSER-START-CONTROLLER.md.

The function requires exactly chrome-alma, numeric CDP port 18802 and UID 1059
before making any service request or localhost health check. Root execution,
another UID, an unsupported platform or another configuration returns
UNEXPECTED_BROWSER_BINDING. The existing return shape, ok/error, is retained.

It calls the generic client with fixed argv and a forty-second timeout, with
stdout/stderr discarded. Failure returns SERVICE_CONTROL_UNAVAILABLE, without
falling back to sudo or probing the browser. It validates the controller path
even if Chrome is already healthy. A successful controller response is followed
by the existing checkChrome call; its health result is returned unchanged.
There are no changes to Google authentication, the profile, query content,
document access or Paco/Salvador's per-query authority.

The source preflight can be run from the reviewed checkout, without installation:

```sh
python3 hosts/vps/identity-network/proposals/check_notebooklm_source.py
```

It only reads code and prints source_ready plus a candidate hash. It refuses the
entire source hash drifting, a missing/duplicate function or an unexpected source
fragment. It writes nothing and always reports deployable=false and
enforcement_applied=false. It has not been run on the VPS; baseline fingerprints
were obtained with ordinary read-only source inspection. Do not apply the patch
based solely on source_ready: the lifecycle/network pilot is still incomplete.

The fixture wake-before.txt is captured existing source, including its original
comment. It is evidence for exact patch matching, not new policy or instructions.
Node tests execute only the proposed function in a fake context. They neither
import nor execute the real NotebookLM backend. The patch test uses a disposable
file with the captured function at its original line offset and checks that no
other bytes change. It is not a functional test against a live Google session.

## Idle-observer blockers and required joint change

The current thirty-minute idle logic checks host ss output. It redirects errors
away and treats a failed command like no established connection. Once a previous
timestamp exceeds the threshold, that can lead to stopping Chrome without a
valid observation. No failure was induced on the host; this is a source finding.

Changing only the namespace of ss is insufficient: there is a race between an
idle check and a new query, and a query can temporarily lack an established TCP
connection. The complete pilot must therefore include all of the following:

1. A per-binding lifecycle lease held for the entire browser operation, from
   before wake/start through final browser disconnect. A fixed start request
   alone does not hold that lease for the subsequent query. All real wrapper
   branches and supported direct clients must participate or block cutover.
2. The observer acquires an exclusive lease before deciding or stopping. The
   start handler and clients coordinate with that same lease so start and stop
   cannot race. Root-managed lease files must not be replaceable by a persona.
3. Observer namespace equality is verified against the approved browser binding.
   A missing or unexpected namespace must never silently select the host stack.
   Socket observation must run in that namespace, without querying CDP contents.
4. An observation error, malformed state, busy lease or uncertain lifecycle must
   never count as permission to stop. Record failure or skip safely. Preserve
   the declared thirty-minute threshold and five-minute timer. Account for boot
   identity and monotonic time instead of trusting an old wall-clock timestamp.
5. Validate the complete units, privileges and writable runtime paths, then test
   active queries, idle expiry, observation failure, simultaneous wake/stop and
   namespace mismatch with fake backends before seeking application approval.

No lifecycle-lease implementation or idle-stop patch is claimed in this commit.
The existing observer must not be combined with this client candidate as though
that completed the pilot. DNS/NAT, shared dependencies, all execution paths,
rollback, host verification and live isolation acceptance remain pending too.
