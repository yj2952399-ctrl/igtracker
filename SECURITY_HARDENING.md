# Security hardening notes

## Changes in this build
- Role assignment is constrained server-side to exactly one rank below the actor.
- A non-root account cannot change its own role or operate on itself through admin target routes.
- Role-matrix editing/reset is restricted to the configured root administrator.
- `roles.json` cannot grant role-management, admin-console-password, purge, or backup-all capabilities to non-admin roles; critical permission checks are also enforced in routes.
- Matrix writes are atomic and failures are surfaced instead of silently reporting success.
- Account creation no longer overwrites an existing username/password/role.
- Account deletions write a tombstone; backup restore skips tombstoned accounts to prevent stale backups resurrecting deleted accounts.
- Shared backups include role-matrix and lockdown configuration files where present.

## Required deployment settings
Set `ADMIN_USER` and `ADMIN_PASS` to the one account that must be the root administrator. Keep `BACKUP_REPO` private and `BACKUP_TOKEN` secret. Use durable storage for `data/` (or `TENANT_ROOT`) and the backup service. Do not commit secrets or production databases to Git.

## Last-resort recovery
1. Stop the application immediately.
2. Take a copy of the current `data/` / `TENANT_ROOT` and backup repository before changing anything.
3. Rotate `ADMIN_PASS`, revoke/replace `BACKUP_TOKEN`, and set `ADMIN_USER` explicitly.
4. Deploy from a known-good source archive and restore only a reviewed backup.
5. If an account must remain deleted, preserve `data/deleted_users.json` (or the configured `DELETED_USERS_FILE`) alongside backups. Remove a tombstone only when intentionally recreating that username.
6. For an active incident, disable public signup (`SIGNUP_OPEN=0`), stop external access at the hosting/network layer, and review audit logs before reopening.

No automated patch can guarantee that every vulnerability is eliminated; perform deployment-specific testing and independent review before production use.
