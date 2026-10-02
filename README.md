# Actor Connection — playable prototype

## Fastest way to play on a Mac

1. Copy this whole `actor-connection-mvp` folder to the Mac.
2. Double-click `START_GAME.command`.
3. The game opens in the default browser at `http://127.0.0.1:8787`.
4. Keep the Terminal window open while playing. Close it when finished.

**No API token is required for the included prototype.** It starts in zero-setup demo mode.

## What works now

- Server-verified puzzle generation: a starting actor is never served unless a route to the weekly target exists within six degrees.
- Movie → co-star validation happens on the backend.
- Movie autocomplete starts only after the player types.
- Co-star autocomplete starts only after a movie is selected and the player types.
- Six-degree limit.
- Backtracking without resetting the clock.
- Invalid moves reveal only `Invalid connection`.
- Two-stage hints are generated from one verified route.
- Finished routes are revalidated server-side.
- Results can show the server's verified shortest route.
- No player-facing database/API credentials.

## Current limitation

The bundled zero-setup database is deliberately small. It proves the full game loop works, but it does **not** yet know every legitimate actor/movie connection. Full arbitrary play requires the production movie graph/data source.

If `TMDB_API_TOKEN` is configured on the server, the prototype switches to live-data mode automatically. That credential remains server-side and is never sent to the browser.

## Production work still needed

- Build/import the large actor/movie graph so arbitrary legitimate routes work quickly.
- Add the eligibility layer needed to exclude end-credit-only appearances while preserving allowed self/uncredited roles.
- Replace bounded live graph crawling with precomputed shortest-path data.
- Add production actor-image licensing/data handling.
- Finalize difficulty scoring, scoring/hint deductions, Daily Challenge, accounts, sharing, and rankings after core playtesting.
