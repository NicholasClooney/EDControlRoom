# Haul Status
## Current
- Market sell routines now merge the hidden-cargo subset from `Cargo.json` back into the demand-sorted `Market.json` sell list so hidden commodities no longer misindex later sale rows.
- Two-way `haul` remains the primary operator path.
- Standalone `multi_leg_haul` / `mult` handles finite external JSON or Spansh-driven routes without changing the two-way haul flow.
- Multi-leg resume derives state from live journal, cargo, and market data instead of persisted routine state.
## Caveats
- Station automation still assumes `DockingGranted`/`Docked` on arrival and `Music` `NoTrack` as the clear-of-station cue after launch.
- Multi-leg flow still needs live validation for repeated stations, consecutive trades, and final-leg completion semantics.
## Next
- Live-validate both two-way and multi-leg haul around resume, station-role detection, and post-launch routing behavior.
