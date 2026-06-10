# Session Log

_This is the rolling short-form log for recent sessions. Keep entries concise and operational. Hard limit: 20 lines. If a new entry would exceed the limit, append the full current log to `docs/status-archive.md`, then reset this file to a fresh empty log template before writing the new entry._

## 2026-06-10

- Renamed the active docs surface to `EDControlRoom` and removed lingering old-project branding from README, AGENTS release-title guidance, and the maintained Control Room operator doc.
- Reviewed haul station-automation assumptions: current flow hard-waits on `DockingGranted`/`Docked` for arrival and `Music` `NoTrack` after `Undocked` for launch clearance; routing and FSD engage themselves are independent of auto-alignment.
- Tightened README and Control Room haul docs to describe the commander-facing handoff more explicitly: EDAP handles post-drop station chores, primes the FSD after station clearance, then uses TTS as the ready-to-jump cue.
- Confirmed a CrossOver/Elite bindings caveat for future troubleshooting: if a shared `Custom` `.binds` preset contains controller mappings, Elite may refuse to surface/load that preset until the mapped controller is connected or otherwise visible to the runtime.
- Preemptive trim of `docs/STATUS.md` (Current Snapshot, Active Capabilities, Key Caveats each kept to top 5 newest bullets) and a full session-log reset to status-archive, restoring headroom before the next handoff.
