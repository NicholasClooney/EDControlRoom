from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


DEFAULT_BACKUP_DIR = Path("backup/bindings")


@dataclass(frozen=True)
class BindingsFileEntry:
    path: Path
    modified_at: datetime

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class PresetFileEntry:
    path: Path
    modified_at: datetime
    preset_name: str

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
    if selector.isdigit():
        index = int(selector)
        if 1 <= index <= len(entries):
            return entries[index - 1]

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


def list_backup_files(backup_dir: Path = DEFAULT_BACKUP_DIR) -> list[BindingsFileEntry]:
    if not backup_dir.exists():
        return []
    return list_bindings_files(backup_dir)


def list_default_preset_files(bindings_file: Path) -> list[PresetFileEntry]:
    entries: list[PresetFileEntry] = []
    seen_paths: set[Path] = set()
    for control_schemes_dir in _control_schemes_dirs(bindings_file):
        for path in sorted(control_schemes_dir.glob("*.binds"), key=lambda item: item.name.lower()):
            if not path.is_file() or path in seen_paths:
                continue
            seen_paths.add(path)
            entries.append(
                PresetFileEntry(
                    path=path,
                    modified_at=datetime.fromtimestamp(path.stat().st_mtime),
                    preset_name=_read_preset_name(path),
                )
            )
    return sorted(entries, key=lambda entry: (entry.preset_name.lower(), entry.name.lower()))


def restore_bindings_file(source: Path, target: Path) -> None:
    shutil.copy2(source, target)


def apply_preset_to_bindings_file(source: Path, target: Path) -> None:
    source_tree = ET.parse(source)
    source_root = source_tree.getroot()

    if target.exists():
        target_root = ET.parse(target).getroot()
        for key in ("PresetName", "MajorVersion", "MinorVersion"):
            if key in target_root.attrib:
                source_root.attrib[key] = target_root.attrib[key]

    ET.indent(source_tree, space="\t", level=0)
    source_tree.write(target, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def _control_schemes_dirs(bindings_file: Path) -> list[Path]:
    candidates: list[Path] = []
    roots: list[Path] = []

    for parent in bindings_file.parents:
        if parent.name == "drive_c":
            roots.append(parent)
            break

    anchor = Path(bindings_file.anchor) if bindings_file.anchor and bindings_file.anchor not in {"/", "\\"} else None
    if anchor is not None and anchor.exists():
        roots.append(anchor)

    seen: set[Path] = set()
    ordered_roots: list[Path] = []
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        ordered_roots.append(root)

    patterns = [
        "Program Files (x86)/Steam/steamapps/common/Elite Dangerous/Products/*/ControlSchemes",
        "Program Files/Steam/steamapps/common/Elite Dangerous/Products/*/ControlSchemes",
        "**/Elite Dangerous/Products/*/ControlSchemes",
    ]
    for root in ordered_roots:
        for pattern in patterns:
            for path in root.glob(pattern):
                if path.is_dir():
                    candidates.append(path)

    unique = sorted(set(candidates), key=lambda path: str(path))
    return unique


def _read_preset_name(path: Path) -> str:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return path.stem
    return root.attrib.get("PresetName", path.stem)
