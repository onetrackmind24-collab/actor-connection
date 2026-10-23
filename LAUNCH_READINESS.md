# Browser launch readiness — October 23, 2026

Planning targets: public beta October 19; full browser launch October 26. These are estimates, not commitments. A licensing delay or critical beta defect moves the dates. Native app launch is outside this browser release.

## Evidence

Version47 was verified live: saved route/hints survived deployment and unavailable-invitation recovery, the restored address matched the round, and refresh resumed directly. Version48 validates reverse hint connections independently and bounds cold credit revalidation. Local45 backend/backup tests and frontend recovery suite passed; v48 live detour/negative-score/result recovery/challenge checks also passed. v49 refreshes the weekly preview when requesting a fresh game. Live John Turturro-to-Tom Hanks solve105 confirmed terminal route rejection before result submission, unchanged route/penalties, successful result, stable result retries and finished recovery. All27 target/difficulty combinations passed startup verification. These checks are not full device or concurrency/load testing.

## Release gates

- Confirm TMDB permission for the intended public/commercial use. Project records do not confirm approval; free player access does not establish noncommercial status. Official terms require a written agreement for commercial use, including advertising/intended commercial use: https://www.themoviedb.org/api-terms-of-use . Do not treat the About attribution as commercial permission.
- Finish actual iPhone/Safari and Android/Chrome manual tests: each difficulty, no-hints, custom and scored challenges, autocomplete, both hint levels, backtrack, give-up, refresh, interrupted requests, final result and sharing. Cloud Chrome and VM tests do not establish Safari coverage.
- Integrate and test the chosen rewarded-ad provider before an ad-supported launch, including success/cancel/no-fill/network failure and exactly-once hint accounting. Existing business rule: players never pay; optional rewarded hints in all modes retain competitive hint penalties. Do not simulate ad completion.
- Run public beta feedback and resolve all critical defects. Recheck Morgan Freeman weekly rotation October19, while existing challenges keep their frozen target.
- Enable GAME_RELEASE_STAGE=launch at the release gate. Confirm status/invitation/share previews hide targets before gameplay, while creators retain their entered pair. Keep beta previews enabled during current beta.
- Review production privacy/consent requirements against the actual ad integration and data flows; publish accurate notices before collecting ad/analytics data.
- Confirm successful deployment/version markers, private file denial, persistent state and rollback/backup arrangements. The state file's atomic replacement is not an independent backup/restore system.

## Attribution update (v45)

Separate About & Credits page, reachable from the game footer and scoring guide. Uses an unmodified official TMDB logo, sourced from the official logos/attribution page, plus the API terms notice. Main instructions remain clean.

Logo source: https://www.themoviedb.org/assets/v4/logos/v2/blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c.svg
Guidance: https://developer.themoviedb.org/docs/faq and https://www.themoviedb.org/about/logos-attribution .


## Human testing reported October17 evening

User reports responsive moves, backtrack without errors, and new starting actors on fresh-game requests. Device/browser and the remaining matrix were not specified; this is encouraging feedback, not a full mobile/Safari signoff.


## Recovery tooling (v50)

Offline state export/verification and restore into a new directory are implemented in backup_state.py; operational procedure is in OPERATIONS.md. A local stopped-server drill booted the actual game from restored data and continued play with hints/backtrack/revision intact, plus restored invitation and finished result. Committed SQLite WAL results are included. This does not complete the production backup gate: an actual off-server production export, restore drill and scheduling/retention arrangements are still required. No production data was copied or restored by this implementation.

## October19 checks

Morgan Freeman rotated in at Monday midnight New York time, with Denzel Washington next October26. v49 was verified live with all27 startup combinations passed; user reported a further manual test without errors. Device/browser and remaining test-matrix coverage were not specified.

## Startup checkpoint (v51, October22)

An opt-in pre-initialization checkpoint supports the single-instance Render disk
deployment without manually killing its server. See OPERATIONS.md. Production
enablement and log verification are pending at this code checkpoint. Off-server
export, a real production-data recovery drill and recurring retention remain
required; implementing the startup hook does not complete those gates.

## Production recovery verified October23; automatic local backups (v52)

The October22 production checkpoint was verified in Render logs, exported to
the user's Mac, uploaded and independently validated. Restore checks preserved
all 64 result rows, five historical rounds and original challenge settings.
Expired records stayed expired; historical clocks were used only in isolated
tests. A new demo-provider round passed hints, backtrack, solve, save and reload
against restored data. No production failover or live-provider replay was done.

v52 adds daily local snapshots, exclusive access during snapshots while keeping
normal requests concurrent, seven-copy automatic retention and safe backup
health status. Production enablement/log checks are pending at this source
checkpoint. Automatic off-server delivery, external failure alerts and recovery
of deployment configuration remain open. Local snapshots do not replace
off-server protection. Licensing, device testing and ad integration gates
above remain unchanged.
