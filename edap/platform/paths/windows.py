from __future__ import annotations

from os import environ
from pathlib import Path

from .base import GamePaths


class WindowsGamePaths(GamePaths):
    def default_journal_dir(self) -> Path | None:
        userprofile = environ.get("USERPROFILE")
        if not userprofile:
            return None
        return Path(userprofile) / "Saved Games" / "Frontier Developments" / "Elite Dangerous"

    def default_bindings_file(self) -> Path | None:
        localappdata = environ.get("LOCALAPPDATA")
        if not localappdata:
            return None
        bindings_dir = Path(localappdata) / "Frontier Developments" / "Elite Dangerous" / "Options" / "Bindings"
        if not bindings_dir.exists():
            return None
        binds = list(bindings_dir.glob("*.binds"))
        if not binds:
            return None
        return max(binds, key=lambda path: path.stat().st_mtime)
