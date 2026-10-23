# State backup and recovery

The Python standard-library tool `backup_state.py` creates and verifies a ZIP
archive of active rounds, challenge invitations, used starters, eligibility
overrides and the results database. It does not need the game's API token.
Provider cache, environment settings, source code and assets are outside this
archive; source/assets remain in GitHub and deployment settings need their own
recovery record.

## Create a backup

Arrange a maintenance window and stop the serving process, or use an offline
volume snapshot. Run where the data directory is mounted. Merely closing a
browser does not stop other requests. The `--server-stopped` flag is an operator
confirmation, not automatic process detection. The state files and database are
separate stores, so the tool does not claim a transaction-consistent live backup.

```bash
python3 backup_state.py create --data-dir /var/data --output /var/data/make-the-cut-state-2026-10-19.zip --server-stopped
python3 backup_state.py verify --backup /var/data/make-the-cut-state-2026-10-19.zip
```

Active-round state and the results database must exist. Optional invitation,
starter-history or local-override files that have not yet been created are
recorded as absent in the manifest and restored as explicit empty state, matching
the server's defaults. Unreadable or invalid existing state fails rather than
silently omitting progress. If `RESULTS_DB` overrides the
default database location, the CLI respects that environment setting; an explicit
`--results-db /path/to/database.sqlite3` takes precedence.

SQLite's backup API includes committed WAL transactions. Each archive includes
file sizes and SHA-256 checksums, JSON shape checks and a database integrity
check. Existing archives are never replaced. Keep unique, dated filenames.

Copy the verified archive to a separate, access-controlled location off the
Render instance and its persistent disk. A copy on `/var/data` alone does not
protect against losing that disk. This tool does not configure off-server
storage, scheduling, retention or provider-volume snapshots. Those production
arrangements still need to be completed and tested. The runtime worker below
automates local snapshots only.

## Verify recovery before switching production

### Render startup checkpoint

For this single-instance Render service with its attached persistent disk, an
operator can set `GAME_STARTUP_BACKUP_NAME=production-2026-10-22` and deploy.
Render stops the old process before the replacement can mount the disk. Before
the new process loads game state, initializes SQLite or accepts requests,
`server.py` creates and verifies
`/var/data/backups/production-2026-10-22.zip` (using `GAME_DATA_DIR` for the base
directory and respecting `RESULTS_DB`). This must not be enabled where another
process or service can still write the same data. Do not run a second server
manually against the live directory.

The setting is disabled by default and requires an existing data directory,
active-round file and results database. A failure stops startup rather than
silently claiming a backup. Archive files have mode 0600; the backup directory
is created with mode 0700. The startup log prints only the checkpoint path,
never its contents. Check for `Startup checkpoint verified:` in Render logs.

A checkpoint name is immutable: subsequent starts validate the existing archive
without replacing or refreshing it. Choose a new name for a later checkpoint,
or clear the setting to disable the check. This is not a recurring backup or an
off-server copy. Export the archive privately and perform the recovery drill
below; keep original live data unchanged during the drill.

### Restore procedure

First restore into a **new, nonexistent directory**. Restoring over existing
state is refused. The parent directory must already exist.

```bash
python3 backup_state.py restore --backup /var/data/make-the-cut-state-2026-10-19.zip --destination /var/data/recovered-2026-10-19
```

Every archive member is validated before the restore directory is created.
If writing fails partway through, the new directory may contain a partial
restore; do not activate it. Choose a different new directory after resolving
the write failure. The original serving directory and backup remain available.

In a stopped-server maintenance window, set `GAME_DATA_DIR` to the recovered
directory. If `RESULTS_DB` is configured separately, point it to the recovered
`game_results.sqlite3` too. Restart and confirm status, an eligible active round,
its hints/backtracks, an invitation and a cached final result before accepting
new traffic. Retain the original directory for rollback. Reverting to it after
accepting new traffic would omit subsequent progress, so do the checks before
reopening play.

Original creation/expiry timestamps are preserved: active rounds still last six
hours and invitations seven days. Recovery does not extend their lifetimes.
Provider cache rebuilds can make initial requests slower after recovery.

## Automatic local backups (v52)

When `GAME_DATA_DIR` is configured, automatic local backups are enabled by
default. Set `GAME_AUTOMATIC_BACKUPS=0` to disable them. This supports the
existing single-process, single-instance deployment only. Do not add external
writers or start another game process against the same data directory.

The running server checks once per minute and creates a snapshot when no
verified automatic copy exists or the last copy is at least 24 hours old.
Restarts discover and verify the latest automatic archive, so they do not reset
the schedule or create unnecessary duplicates. A missing required state file
causes a reported failure and later retry, not silent omission.

HTTP state operations share a request gate and remain concurrent between
backups. The backup asks for exclusive access, waits for in-flight state
operations to finish, and briefly holds incoming state operations while copying
and verifying JSON plus SQLite state. If it cannot obtain exclusive access
within two seconds, it releases waiting requests and retries on the next check.
The two-second limit covers acquiring access, not the backup's total duration.
Status and static requests do not mutate game state and remain available.
The weekly verification worker uses dry-run generation and does not write
backed-up state. Provider cache writes are outside the backup set.

Runtime snapshots call the internal backup API with an explicit
`writes_quiesced` confirmation while holding that gate. The manifest records
`server_stopped_confirmed=false`, `writes_quiesced_confirmed=true` and
`kind=automatic-local`. The manual CLI still requires a stopped process.

Archives use private files in `GAME_DATA_DIR/backups/automatic-*.zip`.
After a new snapshot is fully verified, retention keeps the seven newest
verified automatic archives. Named checkpoints such as
`production-2026-10-22.zip`, unknown files, corrupt archives and symbolic links
are never pruned. Retention failures are reported; a failed new backup does
not delete old copies. Seven copies do not guarantee seven calendar days
if the server is stopped, busy or storage is failing.

The public `/api/status` exposes only local status, timestamps, interval,
retention count and whether off-server delivery is configured. It does not
expose filenames, archive contents, round IDs, paths or credentials. Successful
snapshots and failures also appear in service logs. No external alerting is
configured. The worker retries failures without taking gameplay offline.

These local copies are on the same Render disk. Off-server delivery requires
R2 configuration as described below. Do not put backup data in the public GitHub
repository or add a public download endpoint.

## Private R2 delivery (v53)

In the existing service's Dashboard Environment variables, add R2_BUCKET,
R2_ENDPOINT (HTTPS S3 endpoint, without the bucket path), R2_ACCESS_KEY_ID and
R2_SECRET_ACCESS_KEY. Keep the bucket private and scope the R2 token to Object
Read & Write on this bucket only. Do not use an account-wide administrator key.
Do not store credentials in GitHub, reports or screenshots. After saving with
Save only, the next code deployment activates the values.

The existing worker uploads the newest verified automatic archive on startup,
then each new daily archive. HTTPS PUT is followed by authenticated GET and a
full SHA256 comparison against the locally verified ZIP. Network work happens
outside the snapshot gate. Keys under automatic/ include the archive hash and
filename. Retrying or restarting uses the same object key; no public URL or
bucket configuration is created. Restarts repeat upload/download verification.
Only the newest archive is delivered; older local archives are not backfilled.
The named October22 checkpoint remains on disk and in its existing Mac copy.

No variables means not_configured. Partial or invalid configuration means
invalid_config without stopping the game. Pending, failed, stale and verified
states distinguish remote delivery from local snapshot health. Verification and
failure timestamps are exposed without credentials, endpoint, bucket name,
object paths or content. HTTP exception messages and response bodies are never
logged. Failures retry after five minutes, do not delete local copies, and do
not block requests. Requests have 20-second socket timeouts and archive/response
sizes are capped at 64 MiB. This is not a hard total transfer deadline.

No remote deletion or lifecycle configuration is performed. Remote archives
accumulate until the owner configures retention; the seven-copy limit applies
only locally. No external failure notification is configured. Recovery: use the
private R2 Dashboard to download a ZIP, verify it with backup_state.py verify,
then restore it into a new isolated directory following the recovery procedure.
The application does not download into or overwrite live game state.

## Verification evidence

Automated tests boot the actual game from a restored archive and verify an
accepted move, Hint2 usage, a used backtrack, the route revision, custom challenge
settings, a finished result, and a further accepted move. Additional tests cover
committed SQLite WAL data, invalid JSON/database, changed archive bytes, unsafe
archive paths and refusal to replace existing data. These local tests establish
the tool's behavior.

October 22–23: a real production archive was created and verified, privately
downloaded off Render, uploaded for verification and restored into isolated
directories. All 64 original database rows matched, all five historical round
records and four cached final results were checked, and invitation previews
preserved their original settings. All five rounds were already expired at
checkpoint time; historical test clocks verified their content without
changing expiry timestamps. A separate current-clock check retained expiry
behavior. A new local demo-provider round passed hints, a backtrack, solve,
save and reload while leaving the 64 original rows unchanged. This was an
isolated recovery drill, not a production traffic cutover or live provider
revalidation. The user retains a Mac copy of the archive.
