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


## October 9, 2026 approved logo and hint bridges (v15)
User approved the cleaned navy/ivory/gold Make the Cut clapperboard logo and explicitly requested its use. Exact approved PNG is assets/make-the-cut-logo.png (1964 x 801); responsive header preserves its aspect ratio and includes accessible Make the Cut alternative text. Only this asset is added to the public-file allowlist; source and state files remain private.
Before broad hint search, try eligible shared-film joins from the current actor to the target or actors on the verified comparison route. Require a verified remaining route within the remaining move count, canonical cast eligibility and the existing eight-second search budget. This improves off-route hints without claiming a globally shortest path or fixing the user's unidentified failing case.
Local tests passed two-step bridge, direct target bridge, remaining-depth rejection, broad-search fallback, cameo rejection, deadline restoration, logo GET/HEAD with exact bytes, and private-file/traversal protection. Python and JavaScript syntax passed. Deployment/live verification pending.


## October 9 live verification and final-result retry
Logo/hint-bridges-v15 verified live: status ready/live and persistent data directory configured; homepage 200 contains approved logo. After Ryan -> Russell -> Ryan -> Russell -> Christian Bale (four moves), hints returned The Dark Knight and Morgan Freeman in 3.36 and 2.42 seconds. Recovery preserved degree four and hint level two. Offered final connection accepted, solved in five. Final result retained two hints and 20-point hint penalty. Unknown user-reported case remains unidentified.
Frontend final-result retry: on offline/non-JSON gateway/error response, preserve pending finish intent and route; show Retry result; freeze further moves, backs, hints and give-up while awaiting result. Explicit retry uses existing idempotent server result endpoint. Successful response clears pending UI and displays result normally. JavaScript syntax and simulated non-JSON 502 then successful retry passed. Pending finish UI is in memory; full-page reload recovery for a result already completed server-side remains a known gap.


## October 9 weekly rotation and completed-round recovery (v17)
User clarified: keep Morgan Freeman and Denzel Washington in rotation; use a new test actor, and eventually support all actors. Initial weekly roster is Matt Damon, Tom Hanks, Morgan Freeman, Denzel Washington, cycling on Mondays at midnight America/New_York including DST. Matt is the current test target (week of October 5), then Tom October 12, Morgan October 19 and Denzel October 26. This seed roster is not an eligibility restriction or exhaustive actor coverage; general provider discovery remains available for an explicitly configured target. Existing explicit WEEKLY_TARGET environment override still pins a target; status exposes rotation_enabled and changes_at so deployment can verify actual configuration. Saved rounds and friend challenges retain their original target.
Curated Morgan-ending routes are adapted to Matt via Invictus and Tom via Gone Baby Gone -> Ed Harris -> Apollo 13 -> Tom Hanks. Stop at first target occurrence. Every complete adapted route is still provider-verified and must meet difficulty minimum and six-move maximum. Existing cast/cameo gates remain. Live canonical validation passed all three bridge edges. Tests passed New York Monday boundary, alternating weeks, DST, explicit override, and 15 demo rounds per target across all difficulties. Full live new-target generation pending deployment verification.
Completed rounds with final_result now survive disk loading within the same six-hour round window. GET /api/round returns saved result for completed rounds; active rounds still hide comparison answers. Frontend restores the result without resubmitting score, and restores pending retry UI after submission failure during resume. Final result includes gave_up for exact display recovery. Tests passed completed-result disk reload, GET recovery, identical repeated POST result, finished backtrack rejection, and recovered-result rendering without network submission. Completed result older than six-hour window still expires. This closes the previously recorded full-refresh/restart recovery gap within that window.


## October 9 Deep Cut attribution clarification (v18)
User screenshot showed Batman v Superman: Dawn of Justice -> Ben Affleck +10. Scoring uses the full actor/movie/actor connection and the lower-billed actor, but the label displayed only the destination actor. User explicitly clarified Kevin Costner's Jonathan Kent role qualifies; keep it valid. No Costner denial rule was committed. Do not override this interpretation because press coverage calls the scene a cameo. Deep Cut rows now include from_actor and display both actors around the movie, preserving the scoring formula. Missing/excluded cast credits cannot receive a bonus through fallback billing. Tests passed Costner -> movie -> Affleck attribution, canonical acceptance in fixture, and zero bonus for absent credit; syntax passed. Existing saved final results without from_actor retain their old label. Previous new-target live tests passed Beginner Kevin Bacon, Intermediate Stanley Tucci and Expert Clifton Collins Jr. targeting Matt Damon, plus completed-result GET recovery.


## October 9 bug fixes: autocomplete and transactional round changes (v19)
User directed continued bug fixes instead of cosmetic additions. Invalidate pending actor autocomplete when a movie is selected or typed; hide stale actor options; suppress dropdown painting and selection while a round action is pending. Starting actions invalidates outstanding autocomplete sequences and hides both dropdowns. JavaScript async test passed old actor response rejection after movie selection and after typing another movie, and busy dropdown selection guards. Syntax passed.
Moves and backtracks now compute their prospective route, hint routes, viability and Deep Cut/free-back totals before committing round changes. A provider exception cannot leave a move applied or a back consumed while returning an error. Backtracking also clears offers. Save final result to database before marking the round finished and caching its response, so database failures remain retryable.
Injected-error local HTTP tests passed move and back failures preserving both memory and disk snapshots; successful retry applying one move/back; database error leaving result unfinished; result retry recording exactly one row and stable repeated response. Transport failures after a completed server action remain an uncertainty requiring round recovery; these transactional changes address calculation/database failures before commit.


## October 9 level-loading clapper animation
User requested moving clackers when choosing a level, authorizing this change after the human-testing pause. Added a gold/navy SVG clapperboard with hinged top-arm CSS animation during difficulty/puzzle loading. Hidden before loading and after success or failure; failed loads re-enable difficulty buttons. Honors prefers-reduced-motion with a stationary board; decorative SVG is hidden from assistive technology and loading region reports aria-busy. Existing approved header logo remains intact. JavaScript syntax and success/error loading lifecycle tests passed. No unrelated gameplay or scoring changes in this commit.


## October 9 clapper minimum visibility
User reported the loading animation disappears too quickly to see. Keep successful level loading visible for at least 2.2 seconds from selection, roughly two full claps. Slow loads receive no additional fixed delay. Errors still display immediately. This only changes the presentation before the round begins; server-authoritative timing is unchanged.


## October 9 single clap and hard cut
User replaced repeated loading claps with one clap followed by a movie-style hard cut to the game, explicitly no dissolve. Hold the board open while the puzzle verifies, with a 700ms minimum establishing beat. When ready, close once over 240ms, then immediately hide loading/show game. No opacity or scene transition. Reduced-motion skips the arm movement and cuts directly. Errors do not clap or enter the game. Timing/single-close and reduced-motion tests passed; syntax passed. Supersedes the earlier 2.2-second repeated-clap presentation.


## October 10 launch hardening: interrupted request recovery (v20)
User resumed ongoing fixes/updates towards launch. Server-owned route_revision increments on accepted moves/backs and appears in action responses and round recovery. New clients submit the expected revision; stale move/back/hint returns 409 without advancing, consuming a back or charging a hint. Old clients remain supported and should refresh to receive protection.
Frontend recovers interrupted move/back responses from the full server snapshot instead of resubmitting. Failed recovery locks gameplay and exposes Recover round; queued clicks and dropdown selections are also blocked. GET-only recovery restores revision, route, actor, hints, elapsed time and free backs; terminal results recover/finish normally. Expired rounds return to level choice and clear only expired saved IDs. Stale hints trigger snapshot recovery.
Regression suite: python -m unittest discover -s tests -v; node tests/frontend_recovery.cjs. Six offline Python tests cover stale back replay, stale move/hint after returning to same actor, invalid revisions, atomic calculation failure, database failure/result retry/disk reload and New York weekly/DST boundaries. Frontend tests cover lost move response, lost back plus failed snapshot fetch, blocked retries, explicit recovery and stale hint recovery. Both suites and syntax passed. Live deployment verification pending.
Remaining launch work: broader actor/provider coverage; resolve negative scoring at six with hints; mobile/Safari human validation; difficulty calibration; earned badges and route-marker polish. Do not claim launch complete. Original unidentified hint case remains unreproduced.


## October 10: verified starter variety (v21)
Curated starters now shuffle copied fresh and recycled pools, with fresh candidates first. Each entry is attempted once before the broader catalog fallback; the prior second pass redundantly checked failed fresh candidates. Original route definitions, roster, eligibility, scoring, and saved rounds are preserved. Seven backend regression tests and the frontend recovery suite pass. Expansion of the featured roster remains pending live credit validation; this change does not claim universal actor coverage.


## October 10: expanded weekly featured roster (v22)
Preserved Matt Damon, Tom Hanks, Morgan Freeman, and Denzel Washington in their existing order. Appended Michael Caine (Batman Begins), Clint Eastwood (Unforgiven), Jack Nicholson (The Bucket List), Scarlett Johansson (Lucy), and Angelina Jolie (Wanted). Each bridge from Morgan Freeman passed live /api/validate using canonical person IDs. Every served curated route is still resolved through live credits; stop at the first target appearance and retain the six-move maximum, direct-co-star starter filter, and all existing eligibility rules. Added offline demo actors and synthetic-popularity fixtures so all nine rotation weeks work without a token. Eight backend tests pass, including all 27 target/difficulty combinations, and frontend recovery suite passes. Current October weeks remain unchanged; the new actors begin November 2, 2026 (New York Monday), with nine-week rotation thereafter. Saved rounds/challenges retain their original target. Universal actor coverage and scoring calibration remain outstanding.


## October 10: six-connection hint scoring (v23)
Implemented the user's original negative-score rule: a solved six-connection route with Hint 1 scores -10, or Hint 2 scores -20, before paid-backtrack deductions. The positive base and Deep Cut bonuses do not offset this special penalty; earned Deep Cuts still determine free backs. Other route lengths, no-hint scoring and unsolved zero scores retain prior behavior. Result display explains the rule and instructions document it. New challenges carry scoring_version=2. Previously issued unversioned challenges use version 1 and retain original scoring for fair comparisons; preview labels those older rules. Completed cached results remain unchanged. Ten backend tests plus frontend recovery suite pass, including an actual six-move API round, negative SQLite persistence, idempotent result retry, challenge comparisons with negative scores, and legacy challenge compatibility.


## October 10: bounded loading and restore requests (v24)
Shared frontend request helper uses AbortController deadlines through both fetching headers and parsing the response body (30 seconds normally; 90 seconds for verified puzzle generation). A timeout returns an actionable retry message; all deadline timers clear in finally. Mutating-action timeouts still use the existing saved-round recovery rather than blindly repeating writes. Resume uses the same bounded helper and distinguishes expired 404/409 from network/server failures; saved IDs survive transient failures. Round-start reentrancy guard and disabled back-to-rules control prevent overlapping starts; all controls and clapper state release on failure. Frontend suite covers stalled headers/body, stalled start release and duplicate-start prevention, saved-round preservation on offline restore, and expiry cleanup alongside previous recovery checks. Ten backend tests remain passing. This bounds waiting; it does not guarantee that Render will always be available or make every movie-data request instantaneous.


## October 10: broader verified starters and gameplay search (v25)
Expanded verified curated routes to eligible co-stars of their first movie. Starter selection uses canonical cast IDs, validates the changed first edge, retains the verified tail, excludes direct target co-stars, honors used-starter tracking, and permits missing photos. Beginner uses the first ten billing rows as recognizability heuristic, Expert later rows (or full cast if small), Intermediate all cast. These bands affect starting difficulty only; gameplay accepts any eligible provider cast member without a fame/seed allowlist. Discovery is bounded to six seconds with verified-seed fallback; whole puzzle generation has a sixty-second cooperative budget beneath the browser's ninety-second deadline. Failed fresh candidates are not rechecked in the broader catalog fallback. Exact name matches precede broader actor search matches, with a new cache key so stale mismatches are not retained. Autocomplete matches normalized accents/punctuation; frontend distinguishes an empty eligible-credit search from offline/service failure. Fourteen backend tests and expanded frontend suite pass, including a starter outside every seed pool with no photo, full-cast rows beyond forty, voice/self/blank-role inclusion, cameo/end-credit/crew/self-loop rejection, exact actor-name matching, and budget restoration. This widens starters through verified first-film casts; it is not a complete actor universe or guarantee of all provider credits' correctness. Long-tail film-credit curation and real-device testing remain launch work.


## October 10: cached hint remaining-move guard (v26)
Continued the gameplay review after v25. Found that a hint cached at an actor could remain valid by film credits but become too long after revisiting that actor later in the round. The cache now invalidates paths whose length exceeds remaining moves, then searches for a shorter verified replacement. If none is found, returns the existing no-verified-hint response without escalating hint usage/penalty. Fifteen backend regression tests pass, including cached-route exhaustion with no additional charge. The frontend remains v25's verified recovery and search code.

The continued name-lookup review also corrected exact matching for people whose known-for department is Directing or Writing. Exact performer matches now precede broad acting matches even for those departments; actual film-cast validation continues to enforce the game rules. person_v3 cache keys prevent earlier mismatches from surviving deployment. Live v25 test runs passed Beginner with J.T. Walsh and Intermediate with Dom Irrera, including both hint levels, backtracking and round recovery, solved result persistence/retry, terminal-action rejection and matching friend challenges; Expert no-hint test remains in progress at this checkpoint.


## October 10: keyboard autocomplete and complete visible rules (v27)
Continued gameplay improvements after multi-level v25 and hint-depth v26 checks. Live Expert no-hint/result/challenge checks passed with Stephen Lee. Live v26 stale hint test with Craig T. Nelson rejected an overlong cached path without increasing hint usage. Browser UI with Taylor Treadwell accepted The Devil Wears Prada to Meryl Streep, and reload restored degree/hints/earned backs.
New autocomplete supports Arrow Up/Down, Enter, Escape, active-option styling, ARIA combobox/listbox/option state and live status feedback. Input changes immediately close old suggestions and clear stale actor text/selection. Choosing a movie/actor or dismissing the list invalidates pending search responses, preventing late queries from reopening or replacing the choice. Choosing an actor focuses Make Connection. Instructions now explicitly list no cameos or end-credit-only appearances alongside no TV, voice/self inclusion and scoring rules. Fifteen backend tests and frontend keyboard/cancellation/stale-response/recovery suite pass. Safari/mobile and exhaustive provider-credit curation remain open; this is not a universal-credit guarantee.


## October 10: completed-round and New Game flow (v28)
Continued gameplay review after v27 keyboard validation in the live browser (Denis O'Hare through The Proposal to Ryan Reynolds, Enter submission and Escape dismissal). Replaced reload-based Play Again with New Game returning to level choice, clearing challenge context and only the challenge URL parameter, preserving unrelated URL parameters/hash, and unlocking hint-mode selection. Successful results mark the frontend round finished, disable gameplay controls, and reject further action callbacks. Keyboard focus moves to the result heading; a fresh game re-enables controls and focuses the movie field; successful move/back recovery refocuses the movie input. Failed six-connection endings now say Six-connection limit reached. Result time honors server zero rather than falling back to client timer. Frontend regression suite covers completed action blocking, exact zero elapsed display, challenge reset without reload, normal puzzle URL, fresh controls and focus, and exhausted title. Fifteen backend tests remain passing. Universal credit curation and mobile/Safari testing remain open.


## October 10 launch pass — v29 movie credit completeness

- Removed the release-date requirement from provider movie CAST credits. Valid movie roles with missing release metadata remain available in search, connection validation, and hints. Crew-only rows remain excluded, and canonical movie-side role eligibility still applies.
- Versioned movie credit caches to movies_v2 so persistent old filtered entries cannot hide valid undated credits after deployment.
- Added an offline provider-backed regression covering undated-film search, voice connection offers, stale cache isolation, malformed-row exclusion, and cameo/crew rejection.
- Previous v28 live browser verification completed: Melissa Leo -> The Big Short -> Brad Pitt -> Se7en -> Morgan Freeman -> Invictus -> Matt Damon; 3 degrees, 2 hints, score 80. New Game returned to difficulty selection with focus, fresh Intermediate Jack Kehler counters and controls reset, and that round survived refresh after deployment. Cleared the stale Connection accepted message on New Game.
- Remaining launch work: wider credit exception curation, mobile/Safari human testing, starter coverage expansion and difficulty calibration. All eligible performers are intended to be playable; do not claim every provider credit or generated starter is exhaustively verified.


## October 10 — repeated weekly rotation verification (v30)

- Added internal explicit-target dry-run generation using the same real generator and starter expansion as normal play. HTTP puzzle requests cannot override targets. Dry runs do not consume starter history, advance cursors, create rounds, write results or challenges, or overwrite active-round files.
- Startup sequential background audit verifies all nine roster targets at Beginner, Intermediate and Expert against live provider credits. /api/status rotation_verification reports pending/passed/failed per combination without revealing solution routes. Overall pass requires every generated route to validate and reach its requested target within 2–6 connections. This is live generation evidence rather than only demo fixture coverage.
- Added regressions for two complete nine-week cycles, every difficulty, exact Monday boundaries including DST offset, active-round target preservation, and friend challenge target preservation after weekly changes. Added audit isolation and snapshot integrity checks.
- Confirmed production rotation_enabled=true, next change 2026-10-12T00:00:00-04:00. Live audit outcome must be checked after deployment; do not claim all 27 live cases passed before report completion.


## October 10 launch planning and mobile preparation — v31

- Live v30 rotation audit completed successfully: all 27 target/difficulty combinations passed against real provider credits on October 10 at 21:41 UTC. Roster generation capability is confirmed; actual Monday production clock transition remains upcoming.
- Weekly schedule now includes next_name. Rules and difficulty screens display the featured actor, next actor and change date explicitly in New York time. Schedule-fetch failures do not block play, late responses cannot overwrite newer schedule data, and manual target overrides do not advertise a scheduled change.
- Improved narrow-screen long-name wrapping, preserved autocomplete image width, explicit 16px gameplay inputs, bottom safe-area padding and visible keyboard focus. Actor photo download failures use a placeholder, and clearing a status message removes the empty message box.
- Provisional planning estimates, not release commitments: public browser beta October 19; browser launch October 26; initial app-store release November 16–30, 2026 if limited in scope and device/store checks pass. Repository currently has no native mobile project or PWA manifest/service worker. Store-account access and actual build/signing/device-testing path are not confirmed. Do not present a responsive website as a completed native app.
- Remaining launch gates: real mobile/Safari testing; broader credit exception review; difficulty calibration; observed calendar-triggered rotation; mobile architecture and store-readiness work if native release is pursued.


## October 10 — hinted movies excluded from Deep Cut rewards (v32)

User correction: a movie revealed by either hint must not award a Deep Cut bonus when used. Both hint levels disclose a movie; record canonical movie IDs for the round, retain them through moves/backtracking and persistent recovery, and exclude every use of those movies from Deep Cut points and bonus free backs. Independently found movies remain eligible. New challenge attempts begin with empty personal hint history. Cached completed results remain unchanged. Older active rounds with hints but no retained disclosure history conservatively suppress unverifiable bonuses on their existing route. Hint responses include recalculated free backs for immediate HUD updates. Regression covers point exclusion, no bonus backs, backtracking/replay, saved recovery, final scoring/retry and fresh challenge disclosure history. All 19 backend tests and frontend checks passed before deployment.


## October 10 — starter difficulty correction (v33)

User feedback: obscure performers appeared in Intermediate; difficulty was unclear. Removed unrestricted full-cast discovery from Beginner/Intermediate starter selection. A reviewed familiarity gate based on curated star/character-actor pools, with a few established additional names, now applies to co-star expansion and broad-catalog fallback. Billing position and transient popularity cannot override that gate. Unreviewed cast discoveries remain available as Expert starters. This changes starter selection only: all eligible movie-cast actors remain valid in connections at every level. UI descriptions now explain the familiarity distinction. Existing rounds/challenges retain their original actors; test new difficulty selection with a fresh round. Regression covers top-billed/high-popularity unknown rejection in lower levels, established character actor placement, and Expert discovery. All 20 backend tests plus frontend regressions passed before deployment. Live 27-combination audit must be rechecked after rollout.


## October 10 — off-route hint timeout fix (v34)

User screenshot: Tom Berenger current actor, hint search limit failure with no penalty; route began Chris Evans -> Deadpool & Wolverine. Added bounded direct/two-film shared-credit hint search prioritizing prominent co-stars, validated through canonical eligibility rules. Reserves half the overall hint budget for known-route bridge and BFS fallback; does not assume no route exists when search times out. Hint BFS returns a first verified route without expensive post-success widening. General adaptive path search now retains a found valid route if a later widening stage times out. Regressions cover Berenger/Inception/DiCaprio/Departed/Damon-shaped join, remaining depth, cameo rejection, restored deadlines, short-search timeout fallback, and preserving an earlier verified route. Startup live audit includes a two-degree Tom Berenger-to-Matt Damon hint probe; confirm off_route_hint_check in /api/status after rollout. Version33's 27 live rotation checks passed, including tightened lower-level starter familiarity pools.


## October 10 — custom actor-pair challenges (v35)

User approved creator-entered start and target actors in Challenge Mode, example Jack Nicholson to Gedde Watanabe, with a two-move route to verify live. Added a dedicated creation screen with full credited names, hints allowed/no hints, bounded server route verification, and a seven-day shareable invitation. No route, Cut, or score benchmark is exposed before play. Creation is restricted to challenge mode, rejects identical/unidentified names or unverified pairs, and never changes weekly target, normal starter selection, or active rounds. Reserve broader search time after short-route search timeout. Unscored custom invitations have no fictitious opponent benchmark; playing and finishing can create the existing score-to-beat challenge. Persisted invitations survive restarts and each attempt starts with fresh hint disclosures. Added custom mode/input/privacy/persistence/playability/no-hints/fallback regressions and frontend duplicate-request/failure/null-benchmark checks. All 26 backend tests and frontend suite passed before deployment. Live example and UI verification remain required after rollout. All prior eligibility, hint bonus exclusions, difficulty, weekly rotation, recovery and scoring rules remain in force.


## October 10 — clean instructions and launch target privacy (v36)

User requested that evolving detailed rules stop cluttering How to Play. Landing now retains only the four movie-connection steps, primary difficulty action and custom challenge action; optional scoring.html reference contains scoring/hint/backtracking/credit details. Added only scoring.html to the public allowlist. Rules remain enforced server-side. User permits weekly/current/upcoming target previews during beta but requires all target actors hidden until gameplay begins at launch. GAME_RELEASE_STAGE defaults to beta; set GAME_RELEASE_STAGE=launch for release. Launch redacts weekly target/schedule and detailed rotation audit from public status; invitation previews return target:null/target_hidden:true, while starting or resuming a game reveals the target. Copied challenge texts and finished-round challenge shares hide target at launch, including cached result recovery. Creators still see their own entered target; recipients see it when accepting. Do not disable beta previews yet. All 27 backend tests plus frontend checks passed. Live Nicholson/Gedde invitation created and opening works; complete two-move gameplay proof before reporting it. Original invitation token preserved in persistent challenge store across redeployments.


### Live verification completed

Version35 custom creation UI resolved Jack Nicholson and Gedde Watanabe, created a private unscored invitation, opened it, and completed a valid two-move solve: Nicholson -> A Few Good Men -> Kevin Pollak -> That Thing You Do! -> Watanabe. Server result: solved, 2 degrees, Deep Cut 0 after hint disclosure, free backs 1, score130 with Cut4 and hint penalty20. Preview benchmark remained null and route stayed private. Do not reveal this solution in the invitation or user-facing share text. Version36 default remains beta with weekly previews; launch setting must be enabled as part of launch, not during current beta.



## October 10 — challenge startup recovery (v37)

Reproduced frontend bug: challenge startup error followed by Rules/regular difficulty selection retained activeChallengeToken and the locked hint mode, causing a supposed regular round to use the old challenge pair. Added explicit Retry Start to retry the same mode/pair, hide normal difficulty options during fixed challenge startup, clear challenge token/benchmark and unlock hint choice when returning to Rules or regular play, preserve unrelated query/hash parameters, and restore difficulty selection after finishing a challenge/New Game. Regression first failed on the retained invitation token, then passed after the fix; also tests successful retry with immutable no-hints mode. Updated the separate scoring reference to explain the 100-point Cut baseline and over-Cut floor; main instructions stay clean. Beta preview and launch target privacy stay in effect.

Additional confirmed business requirements from user: players will never pay; monetization is advertising only. Optional rewarded-ad hints are intended for all modes, including challenges/head-to-head, with an ad for every chosen ad-supported hint and the same competitive hint penalty. No ad provider integration is active in this build; do not add paywalls or free scoring exceptions.

Verification before deployment: all 27 backend tests and frontend regressions passed. Live existing-server checks completed Beginner Sandra Bullock (105), Intermediate John C. Reilly (80), Expert no-hints Jack Riley (403 on hint, intentional give-up0), and a separate Expert Lu Elrod solve with hints (105). Each tested saved-round recovery, final result retry consistency, finished-round mutation rejection, and invitation actor/hint-mode/benchmark preservation. The Expert solve is separate from the intentional no-hints give-up check. Runtime API behavior is unchanged in v37 apart from the build marker; verify updated frontend after rollout.


## October 10 — elapsed-time display (v38)

Found display drift when browser background throttling skips timer callbacks: incrementing once per callback undercounts elapsed time. Start/recovery timers now anchor a wall-clock timestamp plus the saved server elapsed duration and calculate elapsed seconds on each callback. Recovery preserves fractional elapsed baseline; a new game resets the anchor. Final scoring and recorded duration remain server-authoritative. Frontend regression simulates a 90-second suspension with a single callback and checks reset/recovery behavior; entire frontend suite passed. Version37 live startup audit passed all 27 rotation combinations. Existing no-hints/scoring/credits/weekly/challenge/privacy rules remain in place.


## October 11 — hint and saved-round recovery (v39)

Reproduced lost-hint-response bug: the server may record hint usage and remove hinted-movie Deep Cut/free-back rewards while the client leaves its HUD unchanged. Ambiguous hint failures (network, timeout, unreadable response, server error) now recover the authoritative round snapshot without automatically issuing another hint. Successful recovery explains how to request the hint again; definite no-route errors still add no penalty. Failed recovery blocks further gameplay until Recover round succeeds. Expired hints/challenges return to the normal chooser, clear the old invitation token/benchmark, unlock hint choice, restore all difficulty controls and preserve unrelated URL parameters. Saved-round restoration failures retain progress and offer Restore Saved Round, with duplicate restoration/start requests guarded while recovery is pending. Recovered snapshots restore the actual challenge and hint mode rather than retaining a different invitation's settings. All prior eligibility/scoring/privacy/rotation rules remain unchanged.

Verification: regression failed before the fix on the missing authoritative hint snapshot. Frontend suite now covers lost/truncated/server-error hint responses, no-route/no-charge handling, recovery locks, expired challenge cleanup and saved-round retry. All 27 backend tests and frontend suite passed before deployment.


## October 12 — saved challenge opening guard (v40)

Live weekly rotation confirmed Tom Hanks on October 12 at 08:45 New York time, with Morgan Freeman scheduled for October 19 midnight. Existing v39 startup audit still passes all 27 target/difficulty combinations; this is separate from testing newly created rounds after the weekly change.

Reproduced frontend race: Accept Challenge became enabled before checking the saved round, so a quick acceptance could replace a matching saved attempt. Acceptance now remains disabled until the saved lookup finishes; matching rounds restore automatically. If the lookup fails, the invitation retains an explicit Resume My Round option, without clearing saved progress. Selecting normal play while an invitation/saved lookup is pending cancels stale auto-resume and rendering. Acceptance and resume callbacks also reject stale invitations. Tests cover deferred same/different/offline saved lookups, no premature start, matching progress recovery, offline restore choice, and leaving a pending invitation. The regression failed on v39's prematurely enabled button before the fix. All prior rules remain unchanged, including hint bonus exclusions, difficulty pools, hidden launch targets, scoring, eligibility and frozen challenge pairs.


### Version40 live verification completed

October12 fresh Tom Hanks rounds passed: Beginner Ryan Gosling solve105, Intermediate Don Cheadle solve105, Expert Laurel Holloman no-hints403 with intentional give-up0, and a separate Expert Samson Barkhordarian hinted solve105. Each checked backtracking/recovery, result retry consistency, finished mutation rejection and frozen invitation pair/hint-mode/benchmark. Browser reopened the original Nicholson/Gedde custom invitation, requested Hint1, reloaded, observed Accept disabled during saved lookup and automatic restoration with hint1 retained. All27 live target/difficulty startup checks passed on v40. The first gameplay test run was interrupted by deployment restart; the completed rerun used deployed v40.

## October13 — authoritative hint and remaining back counters (v41)

Reproduced HUD under-reporting when another copied tab had already used Hint2: a successful Hint1 response only described the requested level, so the client could show1 while the server charged2. Hint responses now include authoritative hints_used and backtracks_used; frontend preserves the highest recorded hint usage. Move responses also include saved backtrack usage. A repeated lower hint retains the same movie and does not add another disclosure or alter scoring.

The free-back HUD previously displayed the full allowance even after consuming it. It now says Free backs left and displays max(0,free_backs-backtracks_used), including earned or removed Deep Cut allowance and round recovery. Backtrack confirmation states remaining allowance; final HUD refreshes from authoritative result counters. The separate scoring reference explains the remaining counter and removal of rolled-back Deep Cut rewards. Main instructions remain clean. Scoring, paid-back calculation, hint penalties, credit eligibility, target privacy and all other rules are unchanged.

Regression tests failed before the fix on frontend hint1-versus2 and missing server hints_used response. After the fix all28 backend tests and the full frontend suite passed. Frontend covers already-used higher hint level, consumed free backs, recovered earned allowance and paid-back feedback. Backend covers repeated Hint1 after Hint2, persisted usage, consistent movie and no extra disclosure. Live UI and API verification remain required after rollout.


## October13 evening — difficulty names and expired result recovery (v42)

User selected Casual / Film Buff / Cinephile to replace Beginner / Intermediate / Expert, in that order. Apply labels to chooser, gameplay badge, challenge invitations and copied result sharing; keep internal beginner/intermediate/expert identifiers to preserve existing saved rounds, challenges, starter pools and scoring history. Custom invitations display Custom Challenge.

Reproduced stuck-result bug: an expired round's Give Up or Retry result left pendingFinish locked forever with no way to choose a new game. Confirmed Puzzle expired or unknown from result now clears only the expired saved round, pending-result/sync locks and old challenge settings, hides retry buttons and returns to the normal chooser. Temporary network/server errors still retain progress and Retry result. Common expiry handling is reused for interrupted action recovery. Regression first failed on retained pendingFinish; covers direct result expiry, expiry after an interrupted result, and starting a fresh round afterward.

Version41 live checks completed: Ryan Gosling to Tom Hanks solved100 after Hint2 then Hint1, two backtracks (first free, second5), saved recovery, no hinted-film Deep Cut rewards and consistent retried final result. Browser Jennifer Lawrence round retained hint2 and zero free backs after a free backtrack/reload.


### Version42 live verification completed

Renamed chooser rendered Casual, Film Buff, Cinephile. Film Buff started a normal Don Cheadle-to-Tom Hanks round with the Film Buff badge, preserving intermediate backend identity. All28 backend tests and frontend regressions passed, including direct expired result and interrupted-then-expired result returning to a usable chooser.

## October14 — confirmed saved progress (v43)

Reproduced persistence error: save_active_puzzles suppressed atomic-write failures, acknowledging moves/results as successful even when they existed only in process memory. Save failures now propagate a clear retry message without exposing filesystem details. Atomic writing snapshots the top-level round map before encoding. In-memory accepted revisions/results are retained so interrupted requests can recover without duplicate moves, hint penalties or results. /api/round retries writing before acknowledging saved progress; cached /api/result retries also persist the accepted cached result before returning success. While writing remains unavailable, recovery/result retry returns an error and the existing frontend guards preserve the pending state. Once storage recovers, saved snapshots survive process reload and the same result/challenge is returned. This improves acknowledgement and retry behavior; it cannot recover an unsaved in-memory action if the process dies during a storage outage.

New fault-injection tests first failed because both move and result returned200 during failed atomic replacements. Tests cover old file preservation, recovery remaining blocked while writes fail, recovered accepted move revision without duplicate replay, failed/cached result retry, one database row, and stable finished result after reloading active state. All difficulty names, scoring, privacy, eligibility, weekly rotation and challenge rules remain unchanged.


All30 backend tests and the frontend suite passed before v43 deployment. Initial main update remained v42 on live status after repeated rollout checks. Added an application-version meta tag to the page to verify frontend/server release agreement and retrigger the normal deployment with a frontend file change. The marker is metadata only; it adds no implementation details to player screens. Update this marker alongside the server build identifier in future releases. Do not report v43 live until both versions are verified.


### Version43 live verification completed October15

After the user's manual Render deploy, both server status and frontend application-version matched v43. All27 target/difficulty startup checks passed. A fresh Film Buff John C. Reilly-to-Tom Hanks solve105 passed backtracking, saved recovery, final-result retry, finished mutation rejection and frozen challenge actor/hint/benchmark preservation. The original Nicholson/Gedde invitation remained intact across the deployment. Auto-deployment did not pick up the v43 commits earlier; do not assume later commits are live without verification.

## October16 — freeze completed routes before saving results (v44)

Reproduced a server-side gap after reaching the target or using the sixth connection but before /api/result succeeds: a delayed request or copied tab could backtrack/change that already-complete route. The existing browser immediately finishes at these boundaries; the backend now enforces the same lifecycle. Moves, backtracks, hints and connection autocomplete reject completed routes with409 and round_changed, without changing the route/revision/hints/backtracks/offers. /api/round and /api/result remain available so progress and pending results can recover, including after restart. No-hints requests still retain their existing403 policy.

Tests first failed on accepted backtracks and changed completed routes. New backend tests cover real demo solves, six unsolved alternating moves, unchanged state/file during rejected actions, restart preservation, and result success/retry. Frontend tests cover the completion409 recovery path for wins and six-move losses, a temporary result-save failure, locked gameplay and result-only retry. All32 backend tests and the frontend suite passed. No change to difficulty labels, six-move rules, scoring, eligibility, weekly rotation, target privacy or existing challenge modes. Frontend/server release markers updated together.


### Version44 live verification completed

Both frontend and server matched v44 without another manual deploy. Live Film Buff John Turturro-to-Tom Hanks solve105 rejected backtrack/hint/move/autocomplete before final submission, preserved the completed route/revision/penalties, then passed result retry and saved finished recovery. Earlier unit suite covered both wins and six-connection losses.

## October16 — attribution and launch readiness (v45)

User requested continued work and an advised launch date. Planning targets: October19 public beta and October26 full browser launch; neither is a commitment. Actual phone/Safari testing, intended-use TMDB permission, beta stability and ad integration remain release gates. See LAUNCH_READINESS.md for explicit evidence and conditions. Do not imply a free beta automatically qualifies as noncommercial when the intended project is commercial. No commercial permission is confirmed in project records; ask for confirmation rather than assume approval.

Added separate About & Credits page with the official unmodified TMDB blue_short SVG (downloaded from TMDB's approved-logo page), source link, and API terms notice. Game footer and scoring guide link to it; gameplay instructions remain unchanged. About and SVG are the only additions to the public-file allowlist. Data-provider credit is not commercial licensing permission. No ads, payments, tracking or launch-stage switch added. Both release markers updated. Private launch notes and source remain denied. All33 backend tests and frontend suite passed before deployment, including GET/HEAD on About/logo and private source/docs/traversal denial.


## October17 — preserve saved rounds when invitations expire (v46)

Reproduced a frontend recovery gap: loadChallenge fetched the invitation before checking saved progress, so an expired invitation or preview outage stranded an otherwise valid round. Invitation preview failure now still checks the saved round. A matching attempt restores automatically, including when its invitation has expired; unrelated rounds require the player to choose Resume My Round. If lookup fails, saved progress remains available for retry. Acceptance stays disabled when invitation preview is unavailable. Leaving the invitation cancels pending recovery. No new attempts are allowed through expired invitations.

Backend regression verifies an attempt started before expiry survives invitation removal on restart, restores its accepted move, finishes normally, preserves its final result across state reload, and expires at its own six-hour boundary. Frontend regressions cover preview404/503 with matching, unrelated, temporarily unreachable and absent saved rounds, plus cancellation while checking a failed invitation. All34 backend tests and frontend suite passed. Scoring, eligibility, difficulty, rotation, privacy, logo, instructions and monetization rules unchanged. Frontend and backend release markers updated together. Deployment and live UI recovery checks pending at this checkpoint.
