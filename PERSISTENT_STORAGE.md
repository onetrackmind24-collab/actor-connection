# Persistent game storage activation

Prepared October 9, 2026. This branch does not change hosting billing or enable a disk.

Render free web services lose filesystem changes when restarted, redeployed, or spun down. Paid web services can attach persistent disks. Official source: https://render.com/docs/disks and https://render.com/docs/free.

## Activate
1. Preserve any existing results database before a redeploy; do not assume current ephemeral data migrates automatically.
2. In the existing Render service, choose a paid compute plan and attach a persistent disk mounted at /var/data. Review the displayed recurring cost before accepting.
3. Set GAME_DATA_DIR=/var/data in the service environment. If RESULTS_DB was set separately, remove it or set it to /var/data/game_results.sqlite3.
4. Deploy this branch (or merge it into main and deploy). Do not create a second service.
5. Restore a prior SQLite backup to /var/data/game_results.sqlite3 while the application is stopped, if one was successfully saved.
6. Complete a test round, record attempts, redeploy, and confirm attempts remain. Also check used starters and eligibility overrides persist.

Mutable state includes results SQLite, active sessions, starter history, eligibility overrides and movie cache. Code stays in the source directory. Existing persistent curated state is never overwritten by repository seeds. Cache retention reduces repeated provider fetches.

## Validation
Syntax and separate-process restart retention tests passed locally with GAME_DATA_DIR pointing to an external directory. Hosting activation and real redeploy retention remain unverified.

Do not mark persistence complete until the actual disk is attached and redeploy test passes. No credentials belong in this document.
