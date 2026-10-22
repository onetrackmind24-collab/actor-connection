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
arrangements still need to be completed and tested.

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

## Verification evidence

Automated tests boot the actual game from a restored archive and verify an
accepted move, Hint2 usage, a used backtrack, the route revision, custom challenge
settings, a finished result, and a further accepted move. Additional tests cover
committed SQLite WAL data, invalid JSON/database, changed archive bytes, unsafe
archive paths and refusal to replace existing data. These local tests establish
the tool's behavior; a production off-server export and recovery drill remain
release gates.
