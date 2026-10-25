# User sessions for system-level PhantomBot ticks

The existing system-level `phantombot-tick@<account>.service` runs as the selected
service account. When a due task needs a detached wake, PhantomBot uses
`systemd-run --user --scope` so the child can outlive the tick's oneshot cgroup.
That needs the same account's running user manager and user bus.

Without that session, dispatch can report `Failed to connect to bus: No medium
found`. In the observed runtime, the plain-child fallback can then access a
database that the dispatcher has already closed. A later idle tick may succeed,
so an intermittent failed state is not proof of an old, resolved incident.

## Scope

This is a host configuration correction. It does not modify PhantomBot, change
persona identity, broaden document access or bypass systemd task isolation.
The drop-in adds the user-manager startup dependency and explicit bus environment
to selected existing tick instances. It preserves the executable, service user,
group, timer schedule, `NoNewPrivileges`, private temporary directory and other
existing hardening settings.

Enabling linger keeps an existing account's user manager available after logout
and across boot. Inspect its enabled user units, including global user defaults,
before doing so: starting the user manager can start those units too. Do not
activate a second persona daemon or re-run native autostart installation.

## Preflight

Use root for system configuration and the selected service account for user-bus
checks. The examples below are synthetic. Replace `example-agent` with one
existing, non-root account whose tick and timer are already provisioned.

```sh
account=example-agent
actor_uid=$(id -u "$account") || exit 1
test "$actor_uid" -gt 0 || exit 1
systemctl cat "phantombot-tick@$account.service"
systemctl show "phantombot-tick@$account.service" -p User -p Group -p ActiveState
systemctl is-enabled "phantombot-tick@$account.timer"
loginctl show-user "$account" -p Linger -p State -p RuntimePath
find "/home/$account/.config/systemd/user" -maxdepth 3 -type l -print
systemctl --global list-unit-files --state=enabled
test -f /usr/lib/systemd/user/dbus.socket
```

An absent session is expected in this incident. Confirm the account from the
actual unit and passwd database; do not derive its UID from a persona label or
reuse a UID from another machine. Review any existing per-instance drop-ins and
whether linger was already enabled. Preserve their bytes and metadata, the unit
definition, recent diagnostics and the previous linger state in a private backup.

## Render and validate

Run from this repository's root. A numeric UID is resolved at installation time;
system-manager `%U` must not be used as a shortcut for the service's `User=`.
The `user@@UID@` template text renders to `user@<numeric-uid>.service`.

```sh
review_dir=$(mktemp -d)
sed "s/@UID@/$actor_uid/g" \
  hosts/vps/systemd/phantombot-tick-user-session.conf.in \
  > "$review_dir/50-user-session.conf"
cat "$review_dir/50-user-session.conf"
systemd-analyze verify --man=no "phantombot-tick@$account.service"
```

The workflow validates a rendered drop-in with a harmless fixture unit using
Ubuntu's native systemd parser. The command above validates the installed base;
validate the effective installed unit again after placing the reviewed drop-in.

## Apply to the selected instance

Do not overwrite an existing `50-user-session.conf` without reviewing its backup.
Install only that file; never replace the account's systemd directory.

```sh
install -D -m 0644 "$review_dir/50-user-session.conf" \
  "/etc/systemd/system/phantombot-tick@$account.service.d/50-user-session.conf"
systemd-analyze verify --man=no "phantombot-tick@$account.service"
loginctl enable-linger "$account"
systemctl start "user@$actor_uid.service"
systemctl daemon-reload
```

No restart of the persona daemon, viewer or timer is needed. Existing ticks finish
normally; the next timer activation uses the drop-in. Do not run an extra real
tick merely to test it, because that can dispatch production work.

## Verify

First confirm the user bus and a harmless scoped command using the existing
systemd programs:

```sh
test -S "/run/user/$actor_uid/bus"
runuser -u "$account" -- env \
  XDG_RUNTIME_DIR="/run/user/$actor_uid" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$actor_uid/bus" \
  systemd-run --user --scope --collect /usr/bin/true
```

Then observe multiple normal timer activations and at least one real task wake.
Check both the journal and the configured application log, including scope
creation, runner startup, stale claims and database exceptions. A green idle tick
alone does not establish that dispatch works. Keep the runtime fallback defect
separate: this configuration prevents the missing-session trigger but does not
repair arbitrary failures in PhantomBot's fallback implementation.

After successful verification, `systemctl reset-failed` may clear only explicitly
identified obsolete transient build/canary units. It does not restart services or
delete the journal. Do not use a blanket reset to conceal recurring tick errors.

## Rollback

Restore the exact prior per-instance drop-in, or remove only the newly installed
file if it did not previously exist, then reload systemd. Preserve diagnostics.
Restore the previous linger setting only after draining active user scopes:
disabling linger or stopping the user manager can terminate live task children.
Do not automatically stop the manager while work is running. A rollback must not
delete user state, identity, task databases or shared configuration.
