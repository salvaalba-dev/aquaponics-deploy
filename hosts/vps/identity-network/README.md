# AU identity network pilot: evidence and proposals

Status: **blocked for deployment**. No VPS change has been applied. These files
are host-specific review material, not the reusable PhantomOrg product policy.

## Read-only findings, 2026-10-15

- Alma runs as pb-alma, UID 1059. Her main, tick and heartbeat services have
  NoNewPrivileges enabled. The running main process reports NoNewPrivs=1 and
  effective capabilities zero. Do not remove this hardening to enable sudo.
- The browser remains bound to Alma's existing profile. Its directory is owned
  by pb-alma, mode 0700. No profile files, cookies or credentials were opened,
  copied or changed during this inspection.
- NotebookLM configuration maps Alma to CDP 18802 and chrome-alma. The actual
  browser client is tools/notebooklm-web.js, called through the persona's regular
  tools/notebooklm-web.sh wrapper. Its on-demand path invokes sudo and
  /usr/local/bin/chrome-alma-ensure. The similarly named notebooklm.sh points to
  scripts/notebooklm.sh and invokes Gemini CLI. These interfaces must not be
  assumed interchangeable; existing knowledge instructions reference that name.
- chrome-alma-idle.timer checks every five minutes, with a thirty-minute idle
  threshold. The root observer uses ss in its own network namespace. After a
  browser namespace migration it would miss private CDP connections unless
  changed, and could stop a browser that is actually in use.
- The ensure helper accepts caller-selected service names after syntax checking,
  and an optional caller-selected port. The sudo rule has no argument constraint.
  This permits broader root service-start requests than its name suggests.
  No attempt was made to start another service or exploit this permission.
- Sudo elevation from the hardened Alma process is independently incompatible
  with its NoNewPrivs flag. A root shell test would not prove tool-path operation.
  No real NotebookLM request, browser start or authenticated-session test was run.

Source fingerprints before any proposed edits:

| Path | SHA-256 |
|---|---|
| /usr/local/bin/chrome-alma-ensure | 4f987f438bfe2f3b027c2eba493ea92f2da8e0d376b2e26fdf421d76ccd9b753 |
| /etc/sudoers.d/90-chrome-alma-ensure | f8b7fb28a618163db6f42e3778fc11d173f1fded44b84c6ba2766e687b1e9074 |

The helper is root:root 0755; sudoers is root:root 0440. Fingerprints are
deployment drift checks, not authorization or signed attestations.

## Confirmed authorization rule

Salvador confirmed on 2026-10-15: preserve explicit approval **for each query**
from Paco (actor paco) or Salvador (human salvador), requested through AU
Coordination. Pepa is not added as an approver by this work.

This agrees with Alma's existing kb/procedures/pipeline-conocimiento.md and
kb/procedures/tools-alma.md. It does not grant either approver browser-session
access. Service start permission is not permission to query NotebookLM.

Portable service policy format 1 supports actor approvers only. Format 2 on the
product's feat/service-isolation-policy branch adds explicit actor/human tags.
Do not misrepresent Salvador as an actor or silently omit him. The accompanying
fragment uses Paco's actor ID and Salvador's human ID verified in the live model.
It is not a complete deployment policy and has not been merged into live org.yaml.
The runtime must still implement the confirmed per-query, either-approver rule.

The authority test checks only the fragment and the actor/human ID registries in
the sanitized snapshot. That snapshot contains literal redaction placeholders
which fail full PhantomOrg shape validation; this check is not a claim that the
entire sanitized org can be built or that a live query has been authorized.
Production validation is not weakened to accept those placeholders.

## Generic controller and AU binding

Reusable implementation and tests now live in the product repository under
persona-service-control, pinned here to commit
6c8fc1dbfb863247466f0f38797e0c32529a6f00. AU contains only its candidate binding,
authority fragment, integration notes and binding tests. The superseded private
Python implementations, fixed units and sudo-helper mitigation are removed from
this branch; they remain available in Git history. This removes proposals from
the repository only, not the existing helper or sudo rule on the VPS.

proposals/alma-browser.binding.json maps UID 1059, account pb-alma and the single
chrome-alma.service start operation. The product derives the control socket from
the binding ID. It contains no browser profile path, credential or port.
proposals/BROWSER-START-CONTROLLER.md explains the boundary and remaining work.

## Required next design

The generic controller is a review component, not deployed. Its renderer produces
review-only units and does not install them. The product CI verifies generated
units and the shared implementation; AU CI checks the candidate assignment and
authority against that pinned code. No test attests the VPS primary group or live
runtime. Client, observer and namespace integration are still needed.

1. Preserve NoNewPrivileges. Use a narrowly scoped external control service,
   reachable through an AF_UNIX socket with filesystem permissions and peer-UID
   checks, for the fixed browser-start operation. Do not grant an arbitrary
   systemctl proxy, port/URL choice, session contents or command execution.
2. Keep the browser and all actual clients together in Alma's namespace. Make
   the root idle observer and root-origin health checks namespace-aware.
3. Represent Paco and Salvador as distinct actor/human approval identities.
   Runtime checks must bind approval to a query, reject stale/unknown approvals
   and prevent bypass through directly accessible CDP/profile credentials if
   technical per-request enforcement is required. Do not claim that compiled
   instructions or a start broker implement this check.
4. Resolve DNS and NAT bindings against the host's routes and firewall; validate
   the complete unit/rule diff on Linux before seeking approval to apply.
5. Test from Alma's actual hardened execution context, plus cross-identity
   synthetic endpoints, persistence and rollback. Preserve existing profiles.

There are no installation commands because the full pilot is not deployable yet.
No units, network rules, credentials or profiles were changed.

Kernel reference for the inherited privilege restriction:
https://www.kernel.org/doc/html/latest/userspace-api/no_new_privs.html
