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
