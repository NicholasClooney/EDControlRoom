# Iteration Log

- Area: `haul`
- Title: `arrival-station-announcement`
- Started: `2026-06-11 18:47`

## Summary

- Moved the post-jump next-station callout into the haul transit routines so two-way and multi-leg haul announce the destination station at hyperspace arrival time.

## Changes

- Shifted the next-station TTS line out of the generic Control Room `FSDJump` announcement path and into the two haul transit flows.
- Added haul coverage for the new announcement timing in the two-way and multi-leg tests.

## Follow-ups

- Live-check the arrival callout timing against the real nav-panel open sequence to make sure the commander hears the station name before panel navigation starts.
