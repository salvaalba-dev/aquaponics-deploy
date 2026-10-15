#!/bin/bash -p
# Proposal only. Install only after operator approval and drift verification.
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin

fail() { printf '%s\n' "$1" >&2; exit 2; }

[[ $# -eq 1 && $1 == chrome-alma ]] || fail 'Only chrome-alma is supported; no port argument is accepted.'
[[ $(/usr/bin/id -u) == 0 ]] || fail 'This helper must run as root.'
expected_uid=$(/usr/bin/id -u pb-alma) || fail 'The Alma account is missing.'
[[ -z ${SUDO_UID-} || $SUDO_UID == 0 || $SUDO_UID == "$expected_uid" ]] || fail 'Unexpected sudo caller.'

readonly unit=chrome-alma.service
private_network=$(/usr/bin/systemctl show "$unit" -p PrivateNetwork --value)
namespace=$(/usr/bin/systemctl show "$unit" -p NetworkNamespacePath --value)
if [[ -n $namespace ]]; then
    [[ $namespace =~ ^/run/netns/[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || fail 'Unsupported namespace path.'
    [[ ! -L $namespace ]] || fail 'Namespace symlinks are not supported.'
else
    [[ $private_network == no ]] || fail 'Anonymous private namespaces require an explicit binding.'
    namespace=/proc/1/ns/net
fi

if ! /usr/bin/systemctl is-active --quiet "$unit"; then
    /usr/bin/systemctl start "$unit"
fi

# Select the service's network namespace explicitly, including for root callers
# outside Alma's namespace. Do not expose CDP response bodies or accept a URL.
for ((attempt=0; attempt<80; attempt++)); do
    if /usr/bin/nsenter --net="$namespace" -- /usr/bin/curl \
        --fail --silent --show-error --max-time 2 \
        http://127.0.0.1:18802/json/version >/dev/null 2>&1; then
        exit 0
    fi
    /usr/bin/sleep 0.5
done
exit 1
