# Make the Cut — project continuity record
Preserved October 8, 2026. Read this before continuing work.

## Recovery scope and authority
This record preserves project information available in the current conversation, supplied prior-conversation summaries, recovered saved source files, and inspected GitHub code. The full "Fact Check Assessment" transcript could not be retrieved: conversation search repeatedly returned an error. This is NOT a complete transcript or a claim that every historical decision was recovered. Missing decisions must remain unknown rather than be invented.
Current implementation authority: https://github.com/onetrackmind24-collab/actor-connection, branch main.
Inspected baseline commit: c969d14cc30c8046e609e763cb6192028205bfd1 (October 8, 2026, 10:09:14 PM Eastern), "Harden actor image handling after valid moves".
Previous commits: 752eec7955f5ef2e7fbc7efc15633f5662bc1457 "Add landing page and connection token validation"; 2c541067e454a49dc4e23c9655236371063601ad "Fix server validation and deployment".
The current server.py matches saved server-offer-token.txt version 2 apart from trailing whitespace. Latest saved server modification: October 8 at 9:46 PM Eastern. Saved index-offer-token.txt is older than the 10:09 PM GitHub image handling correction; use current GitHub index.html.

## Preserved user rules and design requirements
- Movie actor connection game, known as Make the Cut. Weekly featured target actor; randomized starting actor. Denzel was an example, not a permanent target.
- Acting roles only. Crew-only work does not qualify. Cameos excluded. Playing oneself allowed. Voice roles allowed. TV excluded. End-credit-only appearances excluded.
- Actor photographs automatically appear with the actor/puzzle prompt. This supersedes the earlier pictures-only-on-request idea. Photos should also support obscure actors.
- Maximum six degrees/connections. Terminology: "The Cut", replacing "par".
- Solo and two-player Challenge Mode intended.
- One backtrack free; additional backtracks incur deductions. Obscure connections can earn points and additional free backs.
- Detect oncoming failure/dead ends without incorrectly rejecting legitimate routes.
- Actor and film hints; support a no-hints option.
- Historical scoring requirement: base reward for routes under five degrees; obscurity bonuses for rare film/actor connections; negative points possible for a six-degree result with hints. Exact earlier formula is unavailable. Preserve this requirement separately from the implementation below; do not assume it was formally superseded.
- Clean game feel; dark appearance acceptable; no film grain. Badges, clapperboard markers, and movie-style countdown were requested.
- Sharing with friends and weekly actor rotation intended.
- User wants direct critical feedback and meaningful flaws called out.
- User authorized direct GitHub access/corrections and asked to be told if permissions are needed.
- Preserve progress; do not delete earlier chat or source history. Avoid repeatedly asking the user to provide details already available.
- Downloads, copying large code blocks, and browser side panels caused repeated frustration. Prefer direct repository changes and simple usable deliverables.

## Verified implementation as of baseline
Python standard-library HTTP server plus single HTML front end. TMDB live data when TMDB_API_TOKEN is configured; otherwise small demo graph.
- Backend verifies a route of at most six connections before serving a puzzle.
- Difficulty levels beginner/intermediate/expert. Fast curated alpha routes tried before broad live discovery; fresh starters preferred, known good starters recycled when needed. Used starters tracked.
- Canonical validation requires current actor movie CAST credit, next actor in eligible movie CAST, different people; movie-only graph.
- Missing character text does not disqualify a cast credit. Crew-only entries excluded by reading cast arrays.
- eligibility_overrides.json supports curated exceptions, applied to connecting actor eligibility. Repository override file currently empty.
- Movie autocomplete only after typing; connecting-actor autocomplete after selecting a movie and typing.
- Actor autocomplete issues server-approved connection_token; moves use the matching offer rather than requerying the provider; legacy tokenless validation fallback remains.
- Route, current actor, hints and backtracks owned by server. Result ignores client-provided route. Elapsed time derives from server creation timestamp.
- Active rounds stored in active_puzzles.json and restored within six-hour window; results stored in SQLite.
- Hint 1 gives movie, Hint 2 also actor. Both use cached route for current actor. Hint penalty tracked server-side.
- Live search is bounded/adaptive and yields a verified comparison route, not a globally proven shortest route. Demo BFS covers the entire bundled graph.
- Live failed search means unknown, not proof of a dead end. Six moves without target is a dead end.
- The Cut hidden until round ends. Represents competent-player performance rather than automatically the shortest route.
- Exact matchup median used after at least 10 solved results. Median rounded via int(median+0.5), clamped 1–6.
- Provisional Cut = verified route length plus 0–2 based on obscure connections, clamped 1–6. One obscure link adds 1, or 2 when reference-route Deep Cut points >=15; two or more obscure links add 2.
- Current score base = max(25, 100 + (cut - degrees)*25).
- Current Deep Cut route bonus capped at 25. Per-link values 0/5/10/15, estimated from billing depth, movie popularity and age. Both actors among first four billed gives zero.
- Hint deductions 0/10/20 for 0/1/2 hints.
- Free backs = 1 + floor(current surviving route Deep Cut bonus / 10). Rolled-back connections do not count.
- Backtrack deduction = 5 * max(0, total backs used - free backs).
- Solved final score = max(0, base + capped Deep Cut bonus - hint deduction - backtrack deduction). Unsolved score zero.
- Quick Cut display bonus = max(0,(cut-degrees)*25); this efficiency component is already represented in the base formula.
- Latest front-end commit hardens actor images after valid moves.

## Known gaps, conflicts and unresolved issues
- Full old transcript is unavailable, so additional rules/decisions may be missing.
- User reported "still failing" late in prior chat. Latest correction exists, but successful live gameplay was not verified in this recovery session. Do not claim the bug is resolved.
- Current nonnegative scoring conflicts with preserved negative-score design requirement. Under-five historical base requirement also differs from current Cut-relative formula.
- Cameos/end-credit exclusions are not comprehensively enforced by default provider cast credits; curated overrides empty. Current-actor eligibility handling must also be audited before claiming full rule compliance.
- Challenge Mode, no-hints mode, badges/markers/countdown, sharing, rankings, accounts and automatic weekly rotation are requirements/plans, not verified complete features.
- Current default WEEKLY_TARGET is Morgan Freeman. Environment-controlled target is not proof of automatic weekly rotation. Demo people graph does not contain Morgan Freeman; zero-token default startup puzzle generation needs review.
- Existing README describes older behavior and mentions START_GAME.command, which is absent from inspected tree. Treat code as implementation authority.
- Game data and hosting configuration outside GitHub not yet backed up or inspected.
- GitHub connection verified with pull/push rights. Automatic corrections/auto-deployment mechanism itself has not been verified.
- Do not silently change rules to fit code; resolve discrepancies explicitly.

## Deployment and data preservation
Repository contains server.py, index.html, README.md, DEPLOY_TO_RENDER.txt, render.yaml, eligibility_overrides.json, used_starters.json, and blank requirement.text.
Render config: Python web service actor-connection-game, free plan, start python server.py, /api/status health check, HOST=0.0.0.0, PYTHON_VERSION=3.12.7. TMDB_API_TOKEN configured separately as secret (sync false).
Additional server environment names: WEEKLY_TARGET, RESULTS_DB, PORT, HOST, DEV_DIAGNOSTICS. Default local port 8787; diagnostics off unless explicitly enabled.
Never put credential values in source or this record.
Runtime data: game_results.sqlite3 (or RESULTS_DB path), active_puzzles.json, used_starters.json, eligibility_overrides.json, cache/. Repository includes starter/override snapshots but no results DB or active sessions in inspected tree.
render.yaml declares no persistent disk. Runtime durability must be checked at host; GitHub commits alone do not preserve runtime results.
Actual live service URL, current deployment status, secret values and host backups were not recovered.

## Recovered source inventory
29 saved source files recovered, preserving filenames:
Make-the-Cut-server-cutmodel.py
Make-the-Cut-index-quickcut.txt
Make-the-Cut-server-quickcut.py
Make-the-Cut-index-quickcut.html
Make-the-Cut-index-fixed.html
Make-the-Cut-index.txt
Make-the-Cut-index.html
server-offer-token.txt
server-canonical-validation.py
server-canonical-validation.txt
server-latest.txt
server-integrity-fix.txt
server-integrity-fix.py
server.txt
server.py
server-credit-fix.txt
server-credit-fix.py
server-validation-fix.txt
server-validation-fix.py
server-actors-only.py
server-expanded.txt
server-expanded.py
server-fast.txt
server-fast.py
server-fast-pool.py
server-code.txt
index-offer-token.txt
index-landing.html
index.html
Latest saved references: server-offer-token.txt libfile_9946f55348748191b2127a8f52da7ad0, index-offer-token.txt libfile_7c4beffa2ed88191985057cb91227711.
Earlier file names such as server-latest.txt do not establish freshness; compare timestamps, version and GitHub history.

## Continuation instructions
Read this record and current GitHub main before editing. Preserve intended rules and document new decisions here. Verify corrections with actual gameplay and appropriate focused checks. Keep commits recoverable. Obtain the full prior-chat export if exact complete history is required; merge it into this record without losing distinctions between intended, implemented, superseded and unknown details.

## October 9, 2026 verified recovery and responsiveness updates
Live URL recovered: https://actor-connection.onrender.com.
Commit 453763bf10c88b52395ab9c628cbac5460007cca added fast verified-reference hints. Live Hint 1/2 returned in approximately 4/3 seconds.
A complete API round Ryan Gosling -> The Big Short -> Brad Pitt -> Se7en -> Morgan Freeman passed: one free backtrack, replay, two hints, result degrees 2/Cut 2/score 80/penalty 20.
Alternate-route testing then reproduced a 45-second move timeout: accepted moves were blocked by live viability graph search.
Commit c611dce8820d53279687231f2bf1e4c5cc0b59e0 deployed build 2026-10-09-responsive-moves-hints-v3.
- Accepted live moves no longer crawl the graph before replying. Known paths determine viability; unknown stays unknown.
- Known-path BFS combines comparison route and already accepted movie connections, including reverse connections. Returning to a previous actor through a film consumes a normal degree; it is not a free backtrack. This may give a longer but known valid hint; no claim of shortest route.
- Hint search uses actual server remaining degrees, then known routes, then an eight-second cooperative live search budget. Failed searches do not incur hint deductions or declare a proven dead end. Network timeout uses remaining budget; this is not a strict hard wall-clock guarantee against arbitrary slow streaming.
Focused tests passed syntax, off-route bridge, depth limit, timeout handling/context cleanup, and accepted off-route move without live graph crawl.
Live regression passed Ryan Gosling -> The Nice Guys -> Russell Crowe: move accepted in 5.29 seconds; Hint 1 The Nice Guys in 4.92 seconds; Hint 2 Ryan Gosling in 3.16 seconds. The known finish returns via Ryan then Brad Pitt then Morgan Freeman.
Remaining: UI end-to-end verification and fallback-search behavior for routes without a known finish inside remaining moves; runtime data durability/backups remain unresolved. Do not claim all bugs fixed.

## October 9, 2026 persistent storage activated and verified
User upgraded the Render service and reported adding a 1 GB disk mounted at /var/data and setting GAME_DATA_DIR=/var/data.
Activation commit 5a34d4adf71e9931627ba0e8ad6427e188a668df moves results, active rounds, starter tracking, eligibility overrides and provider cache under GAME_DATA_DIR. Existing persisted seeds are never overwritten. RESULTS_DB remains an optional explicit override.
Live status confirmed data_directory_configured=true and results_in_data_directory=true. The previous results database was backed up before deployment and contained zero results.
A test round was recorded (gave up, not solved): total attempts 1, solved 0, provider cache entries 13. Commit f85de60de6e5c3b47b1ab98191b1eff9277d716c triggered another deployment with build 2026-10-09-persistent-state-v4-retention-check. After deployment, live status still showed attempts 1 and cache entries 13: results and cache retention verified across an actual redeployment. Active-round restoration was tested across separate local processes; live active-round retention was not separately asserted.
The test round remains in aggregate statistics. The disk preserves runtime data; it is not an independently verified backup/restore process.
Important configuration distinction: render.yaml still declares the original free plan and no disk; the live paid plan/disk/environment were configured in the Render dashboard. Do not synchronize that old blueprint over the verified dashboard setup without updating it deliberately.
Current source remains GitHub main; current live build is persistent-state-v4-retention-check. Prior durability warnings above describe the baseline and are superseded by this verified update. Remaining gameplay/design gaps above remain open.

## October 9, 2026 project file protection and live active-round retention
Commit 13fb242375377d365a54b0fd7fdb1d333938f62f deployed build 2026-10-09-private-project-files-v5. Previously the static handler served arbitrary project files, including server.py. Static GET/HEAD now only expose / and /index.html; API GET routes retain their existing behavior. Static path translation always maps to the game page, avoiding arbitrary filesystem paths. Local HTTP tests passed normal pages and traversal/file denial.
Live GET and HEAD checks: / and /index.html returned 200; /server.py, /active_puzzles.json, /game_results.sqlite3 and /cache/ returned 404. Render rejected encoded traversal with 400.
Before deployment, a beginner Emma Stone round was created and Hint 1 returned Zombieland (movie 19908). After deployment the same puzzle ID still returned the same hint: live active-round and saved hint persistence verified. The previous test result remained at attempts 1/solved 0. This verifies server restoration across deployment, not a browser refresh/resume UI.

## October 9, 2026 browser refresh recovery
Server commit bd5f1b5bee83d9d3bc650f06207967d25a5aaddd adds GET /api/round?puzzle_id=... exposing only server-owned played progress: start/target/current actor, played route, degrees, hints, backs, earned allowance and elapsed time. It omits The Cut, comparison route, hint answers and connection offers. Missing/expired rounds return 404, finished rounds 409.
Frontend commit 5d9248e39ca6fdeada33fa37171944d2cefa37e5 stores the current puzzle ID in sessionStorage and restores on refresh in the same tab. Successful result submission clears that ID; expired/finished rounds clear it; temporary outages keep it for retry. Storage-disabled browsers continue normal play but cannot auto-resume. The existing six-hour expiry remains; closing the tab is not guaranteed to preserve sessionStorage.
Tests passed Python and JavaScript syntax, actual local HTTP round restoration after module restart with played move/two hints/two backs, answer privacy and finished/missing/expired statuses. JavaScript VM simulation passed reload hydration, elapsed time/route/HUD rendering, expired cleanup, transient failure preservation and disabled-storage handling. This is simulated browser coverage, not visual browser automation. Build marker: 2026-10-09-refresh-recovery-v6. Confirm both frontend and backend are live together; sequential commits can deploy separately briefly.

## October 9, 2026 both-actor eligibility correction
Current-actor movie credits now honor curated exclusions, matching next-actor validation. Movie autocomplete filters those excluded credits. Previously issued offer tokens and saved/reference hint routes recheck exclusions on both sides without a provider graph crawl; known-route reverse edges also honor exclusions. Build 2026-10-09-both-actor-eligibility-v7.
Actual local HTTP tests passed current/next-actor rejection, movie/actor autocomplete, previously issued token rejection after a rule change, cached/reference hint exclusion, no deduction for unavailable hints, and known-route filtering. Positive checks retained provider cast credits with blank character, self and voice labels. Existing acting/crew/TV separation remains based on movie cast endpoints.
Limitation: no comprehensive cameo/end-credit dataset was added. Empty curated overrides still mean those provider cast credits are allowed by default. Do not claim universal cameo/end-credit exclusion. This change fixes enforcement of known exclusions, not automatic classification.
Refresh-recovery frontend and backend were subsequently confirmed live together; the previous Emma Stone round restored with hints_used=1 and hidden answer fields omitted.

## October 9, 2026 automatic labeled-role filtering and curated exclusions
Build 2026-10-09-cameo-credit-filter-v8 rejects explicit cameo and post/mid/end/after-credit annotations in provider character labels. A plain uncredited label is not a cameo classification; voice/self roles and missing character names remain allowed. Current-actor checks inspect both person movie credits and movie cast eligibility. Saved offers and known/reference hints recheck actual credit eligibility, using existing provider caches rather than a graph crawl.
Bundled eligibility_overrides.json now includes two sourced end-credit-only denials: Iron Man (2008), TMDB movie 1726 / Samuel L. Jackson person 2231; Spider-Man: No Way Home (2021), movie 634649 / Tom Hardy person 2524. Sources are stored on each rule. Movie IDs were cross-checked against TMDB listings and person IDs against the live provider-backed person endpoint.
The loader merges bundled rules with disk-backed custom rules at startup, so new repository curation reaches the persistent service. Custom disk rules take precedence for the same actor/movie; existing custom rules remain intact.
Focused tests passed explicit annotations, allowed voice/self/uncredited/blank labels, both directions, stale-route checks, bundled rules with existing custom disk data. Caveat remains: this is automatic filtering of labeled exclusions plus a growing sourced list, not exhaustive classification of every unlabeled cameo in film history. Avoid billing-rank or duration guesses that would erase valid obscure roles.

## October 9, 2026 terminal result integrity
Build 2026-10-09-terminal-results-v9 saves an exhausted six-degree loss as finished, even when the browser did not submit gave_up. Completed rounds reveal the comparison route. Result requests during a still-active unfinished round return 409, closing an early-The-Cut disclosure. Completed result responses are cached on the puzzle so sequential retries return the original score and elapsed time instead of recomputing; the database unique puzzle ID also prevents duplicate rows. Finished rounds remain excluded from restart restoration.
Focused actual HTTP tests passed early-result rejection without finishing, six valid non-target moves saved as a loss, comparison reveal after exhaustion, identical retry response and one result row, finished-round exclusion from restart, ordinary solve and give-up. This does not claim concurrent mutation/submit race protection.
Live cameo-filter-v8 validation previously passed both sourced exclusions in either direction and a positive connection/hint from the retained Emma Stone round.

## October 9, 2026 no-hints mode
Build 2026-10-09-no-hints-mode-v10 adds a Play without hints checkbox before difficulty selection. GET /api/puzzle?difficulty=...&hints=off stores hints_enabled=false in server-owned round state. No later query can turn hints on for that round; both hint levels return 403 without penalties. Default and older rounds keep hints enabled. Recovery and final results expose the round mode; the client hides/disables hint controls and shows a No hints label. No scoring formula was changed.
Actual HTTP tests passed no-hints creation, level 1/2 denial, attempted hints=on query bypass denial, zero hint usage/penalty, recovery and module-restart preservation, default-mode hints, and final result mode. JavaScript simulation passed control visibility/disabled state and label toggling. Server/JS syntax passed.
The prior terminal-results-v9 build passed live early-result rejection and a six-valid-move non-target round: saved once as loss, final comparison revealed, stable result retry, finished recovery returned 409. One additional test loss was recorded; total test attempts became 2 (both unsolved).

## October 9, 2026 result sharing
Share Result is available after a result is accepted by the server. It shares start/target actors, outcome/degrees, solved score/The Cut, difficulty and hint mode, plus the public game URL. It deliberately excludes the played and comparison movie routes. This shares results and invites normal play; it is not a same-puzzle challenge link or two-player Challenge Mode.
Uses native navigator.share on user click, then clipboard when unavailable or failed, then visible selectable read-only text if clipboard fails. Cancellation is silent and restores the button. Tests passed syntax and JavaScript simulation for spoiler-free win/loss summaries, native sharing, copying, cancellation and both APIs blocked fallback. Actual external messages were not sent.
No-hints-v10 previously passed live UI availability, no-hints puzzle creation, both hint levels denied despite hints=on query, and saved mode with zero hints. A no-hints test round was created and left active; no additional result recorded.

## October 9, 2026 earned free-back display
Build 2026-10-09-earned-backs-hud-v11 includes server-calculated free_backs and deep_cut_bank in accepted move responses, using the existing surviving-route Deep Cut formula (one free back plus one per 10 points). The client immediately updates its free-back display from that response. Formula/scoring rules remain unchanged. This calculation uses individual movie/actor credits already used for validation, without a viability graph crawl.
Actual local HTTP checks with a controlled 15-point route bonus passed two free backs on move, ignored client free_backs=999, recovery consistency, bonus removal after rollback and the first back remaining free. JavaScript simulation passed immediate display update. Syntax passed. Sharing controls were previously confirmed present on the deployed live page; real native sharing was not automated.
Separate discovery: demo mode with Denzel target fails Expert generation because bundled Expert starters all have shortest routes below the imposed minimum three. This is a demo-only failure reproduced locally; the live service uses TMDB. Default no-token Morgan target is also absent from the demo graph as documented earlier. Fix demo startup/generation next without weakening live gameplay rules.

## October 9, 2026 score sharing becomes a challenge invitation
User clarified that sharing a score should challenge a friend. Build 2026-10-09-challenge-links-v12 creates an opaque challenge token for every completed server-verified result. The Challenge a Friend button shares score/outcome and an invitation URL /?challenge=TOKEN. It omits The Cut and route answers from the invitation text. Native-share/clipboard/selectable-text fallbacks remain.
Challenges persist in GAME_DATA_DIR/challenges.json using atomic writes under a lock and expire seven days after creation. Tokens contain no embedded route or credential. Public preview returns start/target/difficulty/hint mode/benchmark/expiry, not The Cut, comparison route, source puzzle ID or player progress.
Accepting an invitation creates a new random puzzle ID with the same original actors, difficulty, hint mode, verified comparison route and frozen Cut. It resets route/hints/backs/time, so participants cannot alter each other's rounds. Client difficulty/hint query changes cannot override the stored challenge. Each attempt still has the normal six-hour round limit; active rounds remain separately restorable.
Server comparison: a solve beats an unsolved original; an unsolved attempt loses to a solved original; two unsolved attempts tie. When both solve, higher points wins and equal points ties. Time is displayed but is not a tiebreaker. Results display the outcome and opponent score. This is asynchronous friend Challenge Mode; no accounts, names, live lobby or shared turn-taking were added.
Opening an invitation while another round is saved offers Resume My Round or Accept Challenge. A matching saved challenge resumes. Choosing a regular round clears the invitation URL. Starting a challenge replaces the browser's active-round reference only after successful puzzle creation, as with starting any new round.
Tests passed syntax, actual local HTTP completion/creation/preview, hidden-answer fields, fixed puzzle/cut/mode, query tamper resistance, independent repeated attempts, tie/win/loss comparisons, repeated result response, module-restart invitation persistence and expired-link 404. JavaScript simulation passed acceptance URL/mode/score display, invitation text without Cut, and preserving an unrelated saved round until user choice. Native sharing and visual browser flows were not automated.
Previous earned-backs-hud-v11 live check passed move allowance/recovery consistency and route restoration after backtrack.

## October 9, 2026 demo default target and Expert generation fixed
Build 2026-10-09-demo-default-expert-v13 adds Morgan Freeman and the real Glory connection to the sample graph, verified against Sony Pictures' cast listing https://www.sonypictures.com/movies/glory. Demo mode now works with the existing default Morgan target. Demo's tiny Expert pool permits verified routes of two or more degrees instead of rejecting every Denzel route; live Expert retains its existing three-degree generation minimum. No live cast, score, hint or difficulty rules were altered.
Tests passed all difficulties five successive times each for no-token default Morgan and explicitly configured Denzel. Verified each route ends at target and passes canonical validation. Full actual HTTP Expert rounds passed level-2 hint, every move, solved result and challenge token creation for both targets. Syntax passed.
Live challenge-links-v12 previously passed invitation UI/creation, preview without Cut/route, independent same-actor/mode round, query mode tamper rejection and saved challenge state. A friend test round completed at 100 points with original Cut preserved; the server correctly reported a win against the original unsolved test round. That test added one give-up and one solved result (test aggregate 4 attempts, 1 solved at that point). Asynchronous challenges now supersede the earlier score-only sharing limitation.

## October 9, 2026 concurrent round actions and rapid clicks
Build 2026-10-09-serialized-round-actions-v14 serializes reads/mutations for the same puzzle with per-round reentrant locks; independent rounds keep separate locks. Weak lock references are reclaimed after requests finish, so arbitrary/old IDs do not accumulate permanent locks. State-file writes have a separate lock to prevent different rounds racing on the same atomic-replace temporary file. Bad JSON/non-object POST bodies return 400.
Client round-action guard disables move/back/hint/give-up buttons and movie/actor fields while an action is pending. Rapid second clicks are ignored, controls restore afterward, and no-hints buttons remain disabled. loadCurrent increments autocomplete sequence counters so outstanding old responses cannot repopulate stale options.
Actual concurrent local HTTP tests passed two duplicate moves with one accepted degree; duplicate backs with one back consumed; four simultaneous result submissions with identical response and one stored score; eight different-round finishes with all disk snapshots preserved; lock reclamation; malformed body rejection. JavaScript simulation passed one request for two rapid clicks, frozen inputs during request, post-action reset and no-hints preservation. Syntax passed.
Demo-default-expert-v13 previously passed live Expert generation (David Morse starter), TMDB/live mode and configured persistent storage.

## October 9, 2026 user-reported hint failure remains under diagnosis
User reported Hint unavailable after a move while running their own tests. Current actor was not supplied (user said neither Russell Crowe nor Brad Pitt). Do not mark that unknown case fixed.
Live checks on serialized-round-actions-v14 passed duplicate same-token moves with exactly one advance, recovery degree consistency and backtrack. Hint diagnosis passed fresh Ryan Gosling Hint 1/2 (3.31/3.04 seconds) and Ryan -> The Nice Guys -> Russell Crowe off-route Hint 1/2 (4.09/3.31 seconds). These passing cases do not establish the user's failing route works.
Frontend now exposes the actual hint failure reason instead of hiding all errors as Hint unavailable. Handles non-JSON HTTP errors (including transient Render 502), unreadable success responses and connection failures with understandable messages. Search-limit/no-verified-route message states no added hint penalty and suggests backtrack or another connection; it does not declare a proven dead end.
Tests passed successful JSON response, non-JSON 502, expired-round JSON error, offline fetch and search-limit/no-penalty messages. Need exact current actor/last connection and the new displayed error to reproduce the user's case. Continuous deployments can briefly return 502 during Render restarts; do not assume this was their error without evidence.
