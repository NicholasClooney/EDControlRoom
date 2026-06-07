from __future__ import annotations

import argparse
import json
from pathlib import Path

from edap.runtime import build_runtime_context, load_config_with_fallback
from edap.state import JournalWatcher

INTERESTING_EVENTS = {
    "StartJump",
    "SupercruiseEntry",
    "SupercruiseExit",
    "FSDJump",
    "Undocked",
    "Docked",
}

LOG_PATH = Path("artifacts/journal-watcher.log")


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch Elite Dangerous journal events")
    parser.add_argument("--all", action="store_true", help="print all events, not just filtered ones")
    args = parser.parse_args()

    loaded = load_config_with_fallback("config.toml")
    runtime = build_runtime_context(loaded.config)
    journal_dir = runtime.journal.effective_path

    if journal_dir is None:
        print("Could not resolve journal directory")
        return 2

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Watching journal dir: {journal_dir}")
    print(f"Logging all events to: {LOG_PATH}")
    if args.all:
        print("Showing: all events")
    else:
        print(f"Showing only: {', '.join(sorted(INTERESTING_EVENTS))}")
    watcher = JournalWatcher(journal_dir, poll_interval_s=0.5)

    with LOG_PATH.open("a", encoding="utf-8") as log_handle:
        for event in watcher.watch():
            log_handle.write(json.dumps(event))
            log_handle.write("\n")
            log_handle.flush()

            if args.all or event.get("event") in INTERESTING_EVENTS:
                print(event.get("event"), event)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
