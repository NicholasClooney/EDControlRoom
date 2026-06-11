# Control Room Status
## Current
- Control Room routine launchers now pass `app._time_fn` through jump/dock/undock/market/nav/haul helpers, and cached default message loads trimmed local full-suite runtime from `0.687s` to about `0.245s`.
- Single-commodity `MarketSell` totals now announce sale revenue instead of profit; haul/session profit tracking is unchanged.
- Operator-facing default text is split between `defaults/error_messages.yaml` and `defaults/messages.yaml`, with TOML overrides still supported.
- Routine failures now surface as `Failed:` plus `Try:` guidance instead of raw internal-looking error output.
- Activity-log retention and the repo-local `artifacts/control-room.log` mirror are covered in tests.
## Caveats
- Real-world validation is still needed for stale-market, wrong-station, and wrong-commodity recovery wording.
## Next
- Live-validate the new failure wording and the market back-out path against real Control Room error cases.
