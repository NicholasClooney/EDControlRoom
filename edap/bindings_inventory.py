from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil


DEFAULT_BACKUP_DIR = Path("backup/bindings")


@dataclass(frozen=True)
class BindingsFileEntry:
    path: Path
    modified_at: datetime

    @property
    def name(self) -> str:
        return self.path.name


def list_bindings_files(bindings_dir: Path) -> list[BindingsFileEntry]:
    entries = [
        BindingsFileEntry(
            path=path,
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
        )
        for path in bindings_dir.glob("*.binds")
        if path.is_file()
    ]
    return sorted(entries, key=lambda entry: (-entry.modified_at.timestamp(), entry.name.lower()))


def choose_bindings_file(entries: list[BindingsFileEntry], selector: str | None = None) -> BindingsFileEntry:
    if not entries:
        raise ValueError("no .binds files found in detected bindings folder")
    if selector is None or selector == "latest":
        return entries[0]

    for entry in entries:
        if entry.name == selector or str(entry.path) == selector:
            return entry

    raise ValueError(f"could not find .binds file matching {selector!r}")


def default_backup_name(bindings_path: Path, *, today: date | None = None) -> str:
    stamp = (today or date.today()).strftime("%Y-%m-%d")
    return f"{bindings_path.stem}-{stamp}{bindings_path.suffix}"


def copy_bindings_to_backup(
    source: Path,
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    backup_name: str | None = None,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)

    target_name = backup_name or default_backup_name(source)
    target = backup_dir / target_name
    if target.suffix != source.suffix:
        target = target.with_suffix(source.suffix)

    if target.exists():
        base = target.stem
        suffix = target.suffix
        counter = 2
        while True:
            candidate = backup_dir / f"{base}-{counter}{suffix}"
            if not candidate.exists():
                target = candidate
                break
            counter += 1

    shutil.copy2(source, target)
    return target
