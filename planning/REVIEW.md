# Review: changes in `e05f03e` (`Initial setup`)

Compared commit `e05f03e` with its parent, `14550e1` (`Ready for Teams`). The review excludes this report's contents as a target.

## Findings

1. **[P1] Massive snapshots are skipped because the timestamp field is incorrect.** [`massive_client.py:103`](../backend/app/market/massive_client.py#L103) reads `snap.last_trade.timestamp`, but Massive snapshot timestamps use `sip_timestamp` in nanoseconds (as documented in [`MASSIVE_API.md`](MASSIVE_API.md)). The resulting `AttributeError` is caught and that snapshot is discarded, so real market prices never reach the cache. Read the documented field and convert nanoseconds to seconds; add a test using the actual SDK model shape. The code also assumes `last_trade` and `price` are present.

2. **[P1] README quick start points to files that are absent.** [`README.md:31-34`](../README.md#L31) instructs users to copy `.env.example` and run `scripts/start.sh`, `scripts/stop.sh`, or the Windows start script, but none of those paths exists in the repository. Add the referenced setup files or replace these steps with commands that work from this checkout.

3. **[P2] Market interface docs describe fields missing from the implementation.** [`MARKET_INTERFACE.md`](MARKET_INTERFACE.md) and [`PLAN.md:189`](PLAN.md#L189) specify `session_open` and `session_change_percent` on price updates, but [`models.py`](../backend/app/market/models.py) and [`cache.py`](../backend/app/market/cache.py) do not implement them. The documented SSE/watchlist contract therefore cannot be produced. The interface spec's status table marks this as “To do”; reconcile the status, plan, and API examples with the implementation or implement the fields and update tests.

4. **[P2] The Stop hook can overwrite an existing `planning/REVIEW.md`.** [`hooks.json:8`](../independent-reviewer/hooks/hooks.json#L8) runs in repositories using the plugin and directs Codex to write to that fixed path. If the consuming project already has a review document there, it may be replaced on session stop. Make the hook opt-in or use an output approach that preserves existing content.

## Review scope and checks

Reviewed the 12 commit paths other than this report, including the README, market data specifications, plugin hook, and referenced market implementation. `git diff --check HEAD^ HEAD` reports trailing whitespace in `.claude/agents/change-reviewer.md:11`. No tests were run.
