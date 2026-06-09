from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Protocol

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - exercised on non-POSIX hosts
    termios = None
    tty = None

from edap.bindings_inventory import (
    DEFAULT_BACKUP_DIR,
    BindingsFileEntry,
    PresetFileEntry,
    apply_preset_to_bindings_file,
    choose_bindings_file,
    copy_bindings_to_backup,
    list_backup_files,
    list_bindings_files,
    list_default_preset_files,
    restore_bindings_file,
)
from edap.config import ConfigError, DEFAULT_CONFIG_PATH
from edap.runtime import build_runtime_context, load_config_with_fallback


class _SelectableEntry(Protocol):
    path: Path
    modified_at: object

    @property
    def name(self) -> str: ...


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List detected Elite Dangerous .binds files, back them up, restore backups, and apply shipped presets"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config TOML file",
    )
    parser.add_argument(
        "--bindings-file",
        default=None,
        help="Override bindings file path (otherwise resolved through config)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")

    subparsers = parser.add_subparsers(dest="command")
    backup_parser = subparsers.add_parser("backup", help="Copy a bindings file into the gitignored backup folder")
    backup_parser.add_argument(
        "source",
        nargs="?",
        default="latest",
        help="Bindings filename to copy from the detected folder, or 'latest' (default)",
    )
    backup_parser.add_argument(
        "--name",
        default=None,
        help="Optional backup filename; defaults to <binds-name>-YYYY-MM-DD.binds",
    )
    backup_parser.add_argument(
        "--backup-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help="Backup destination directory",
    )
    restore_parser = subparsers.add_parser(
        "restore",
        help="Restore a backed-up .binds file onto the detected bindings file",
    )
    restore_parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Backup filename, path, or list number; omit to choose interactively",
    )
    restore_parser.add_argument(
        "--backup-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help="Directory that stores backup .binds files",
    )
    apply_default_parser = subparsers.add_parser(
        "apply-default",
        help="Copy a shipped default preset over the detected bindings file after confirmation",
    )
    apply_default_parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Preset filename, path, or list number; omit to choose interactively",
    )
    apply_default_parser.add_argument(
        "--backup-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help="Backup destination directory used before overwriting the detected bindings file",
    )

    args = parser.parse_args()

    try:
        detected_file = _resolve_bindings_file(args.config, args.bindings_file)
    except FileNotFoundError:
        sys.stderr.write(
            f"Config file not found: {args.config}\n"
            f"Pass --bindings-file or create a config.toml.\n"
        )
        return 2
    except ConfigError as exc:
        sys.stderr.write(f"Invalid config: {exc}\n")
        return 2
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    bindings_dir = detected_file.parent
    entries = list_bindings_files(bindings_dir)
    if not entries:
        sys.stderr.write(f"No .binds files found in detected folder: {bindings_dir}\n")
        return 2

    if args.command == "backup":
        return _run_backup(args, detected_file, bindings_dir, entries)
    if args.command == "restore":
        return _run_restore(args, detected_file, bindings_dir)
    if args.command == "apply-default":
        return _run_apply_default(args, detected_file, bindings_dir)
    return _run_list(args.json, detected_file, bindings_dir, entries)


def _resolve_bindings_file(config_path: str, override_path: str | None) -> Path:
    if override_path is not None:
        path = Path(override_path).expanduser()
        if not path.exists():
            raise ValueError(f"Bindings file not found: {path}")
        if not path.is_file():
            raise ValueError(f"Bindings path is not a file: {path}")
        return path

    loaded = load_config_with_fallback(config_path)
    runtime = build_runtime_context(loaded.config)
    bindings_file = runtime.bindings.effective_path
    if bindings_file is None:
        raise ValueError(
            "Could not resolve bindings file. "
            f"Source status: {runtime.bindings.cli_source_status()}."
        )
    return bindings_file


def _run_list(as_json: bool, detected_file: Path, bindings_dir: Path, entries: list) -> int:
    if as_json:
        payload = {
            "detected_bindings_file": str(detected_file),
            "detected_bindings_dir": str(bindings_dir),
            "files": [
                {
                    "name": entry.name,
                    "path": str(entry.path),
                    "modified_at": entry.modified_at.isoformat(timespec="seconds"),
                }
                for entry in entries
            ],
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    sys.stdout.write(f"Detected bindings file: {detected_file}\n")
    sys.stdout.write(f"Detected bindings folder: {bindings_dir}\n")
    sys.stdout.write("Bindings files by most recent change:\n")
    for index, entry in enumerate(entries, start=1):
        modified_at = entry.modified_at.strftime("%Y-%m-%d %H:%M:%S")
        sys.stdout.write(f"{index}. {entry.name}  {modified_at}\n")
    return 0


def _run_backup(args: argparse.Namespace, detected_file: Path, bindings_dir: Path, entries: list) -> int:
    try:
        selected = choose_bindings_file(entries, args.source)
        backup_path = copy_bindings_to_backup(
            selected.path,
            backup_dir=Path(args.backup_dir),
            backup_name=args.name,
        )
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    if args.json:
        payload = {
            "detected_bindings_file": str(detected_file),
            "detected_bindings_dir": str(bindings_dir),
            "source": str(selected.path),
            "backup": str(backup_path),
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    sys.stdout.write(f"Copied {selected.path.name} to {backup_path}\n")
    return 0


def _run_restore(args: argparse.Namespace, detected_file: Path, bindings_dir: Path) -> int:
    backup_dir = Path(args.backup_dir)
    entries = list_backup_files(backup_dir)
    if not entries:
        sys.stderr.write(f"No backup .binds files found in {backup_dir}\n")
        return 2

    try:
        selected = _choose_entry(entries, args.source, label="backup file")
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    current_backup = copy_bindings_to_backup(detected_file, backup_dir=backup_dir)
    restore_bindings_file(selected.path, detected_file)

    if args.json:
        payload = {
            "detected_bindings_file": str(detected_file),
            "detected_bindings_dir": str(bindings_dir),
            "source": str(selected.path),
            "backup": str(current_backup),
            "restored_to": str(detected_file),
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    sys.stdout.write(f"Backed up current bindings to {current_backup}\n")
    sys.stdout.write(f"Restored {selected.path.name} to {detected_file}\n")
    return 0


def _run_apply_default(args: argparse.Namespace, detected_file: Path, bindings_dir: Path) -> int:
    backup_dir = Path(args.backup_dir)
    entries = list_default_preset_files(detected_file)
    if not entries:
        sys.stderr.write(
            "Could not find any shipped default preset files relative to the detected bindings file.\n"
        )
        return 2

    try:
        selected = _choose_entry(entries, args.source, label="default preset")
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    if not _confirm_overwrite(
        f"Overwrite {detected_file.name} with preset {selected.preset_name}? "
        "A backup of your current bindings will be saved first. [y/N]: "
    ):
        sys.stdout.write("Cancelled.\n")
        return 0

    current_backup = copy_bindings_to_backup(detected_file, backup_dir=backup_dir)
    apply_preset_to_bindings_file(selected.path, detected_file)

    if args.json:
        payload = {
            "detected_bindings_file": str(detected_file),
            "detected_bindings_dir": str(bindings_dir),
            "source": str(selected.path),
            "preset_name": selected.preset_name,
            "backup": str(current_backup),
            "target": str(detected_file),
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    sys.stdout.write(f"Backed up current bindings to {current_backup}\n")
    sys.stdout.write(
        f"Applied preset {selected.preset_name} from {selected.path.name} to {detected_file}\n"
    )
    sys.stdout.write("Your previous custom bindings were saved first.\n")
    return 0


def _choose_entry(entries: list[_SelectableEntry], selector: str | None, *, label: str) -> _SelectableEntry:
    if selector is not None:
        selected = _resolve_selector(entries, selector)
        if selected is not None:
            return selected
        raise ValueError(f"could not find {label} matching {selector!r}")
    return _choose_entry_interactively(entries, label=label)


def _resolve_selector(entries: list[_SelectableEntry], selector: str) -> _SelectableEntry | None:
    candidate = selector.strip()
    if candidate.isdigit():
        index = int(candidate)
        if 1 <= index <= len(entries):
            return entries[index - 1]
    for entry in entries:
        if entry.name == candidate or str(entry.path) == candidate:
            return entry
    return None


def _choose_entry_interactively(entries: list[_SelectableEntry], *, label: str) -> _SelectableEntry:
    if not entries:
        raise ValueError(f"no {label} entries available")

    stdin = sys.stdin
    stdout = sys.stdout
    if not hasattr(stdin, "isatty") or not hasattr(stdout, "isatty"):
        return _choose_entry_by_number(entries, label=label)
    if not stdin.isatty() or not stdout.isatty():
        return _choose_entry_by_number(entries, label=label)
    if os.name == "nt" or termios is None or tty is None:
        return _choose_entry_by_number(entries, label=label)

    index = 0
    query = ""
    while True:
        visible_entries = _filter_entries(entries, query)
        if not visible_entries:
            index = 0
        elif index >= len(visible_entries):
            index = len(visible_entries) - 1

        _render_selection_menu(entries, visible_entries, index, label=label, query=query)
        key = _read_key(stdin)
        if key == "\x03":
            raise ValueError("selection cancelled")
        if key in ("\x1b[A", "k"):
            if visible_entries:
                index = (index - 1) % len(visible_entries)
        elif key in ("\x1b[B", "j"):
            if visible_entries:
                index = (index + 1) % len(visible_entries)
        elif key in ("\x7f", "\b"):
            query = query[:-1]
            index = 0
        elif key in ("\r", "\n"):
            if query and query.isdigit():
                selected = _resolve_selector(entries, query)
                if selected is not None:
                    stdout.write("\n")
                    return selected
            elif len(visible_entries) == 1:
                stdout.write("\n")
                return visible_entries[0]
            elif visible_entries:
                stdout.write("\n")
                return visible_entries[index]
        elif key.lower() == "q":
            raise ValueError("selection cancelled")
        elif len(key) == 1 and key.isprintable():
            query += key
            index = 0


def _choose_entry_by_number(entries: list[_SelectableEntry], *, label: str) -> _SelectableEntry:
    sys.stdout.write(f"Select a {label} by number:\n")
    for index, entry in enumerate(entries, start=1):
        sys.stdout.write(f"{index}. {_entry_label(entry)}\n")
    sys.stdout.write("Type a number or a prefix filter: ")
    try:
        choice = sys.stdin.readline().strip()
    except KeyboardInterrupt as exc:
        raise ValueError("selection cancelled") from exc
    filtered_entries = _filter_entries(entries, choice)
    if len(filtered_entries) == 1:
        return filtered_entries[0]
    selected = _resolve_selector(entries, choice)
    if selected is None:
        raise ValueError(f"could not find {label} matching {choice!r}")
    return selected


def _render_selection_menu(
    entries: list[_SelectableEntry],
    visible_entries: list[_SelectableEntry],
    selected_index: int,
    *,
    label: str,
    query: str,
) -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.write(
        f"Select a {label} with up/down and Enter, or type a prefix filter / number"
    )
    if query:
        sys.stdout.write(f" [{query}]")
    sys.stdout.write(":\n\n")
    if not visible_entries:
        sys.stdout.write("  (no matches)\n")
    for index, entry in enumerate(visible_entries, start=1):
        marker = ">" if index - 1 == selected_index else " "
        sys.stdout.write(f"{marker} {index}. {_entry_label(entry)}\n")
    if query:
        sys.stdout.write("\nBackspace deletes. Ctrl-C or q cancels.\n")
    sys.stdout.flush()


def _entry_label(entry: _SelectableEntry) -> str:
    if isinstance(entry, PresetFileEntry):
        return f"{entry.preset_name} ({entry.name})"
    if isinstance(entry, BindingsFileEntry):
        modified_at = entry.modified_at.strftime("%Y-%m-%d %H:%M:%S")
        return f"{entry.name}  {modified_at}"
    return entry.name


def _filter_entries(entries: list[_SelectableEntry], query: str) -> list[_SelectableEntry]:
    candidate = query.strip().lower()
    if not candidate or candidate.isdigit():
        return entries
    filtered: list[_SelectableEntry] = []
    for entry in entries:
        labels = [entry.name.lower(), str(entry.path).lower()]
        if isinstance(entry, PresetFileEntry):
            labels.append(entry.preset_name.lower())
        if any(label.startswith(candidate) for label in labels):
            filtered.append(entry)
    return filtered


def _read_key(stream: object) -> str:
    assert termios is not None
    assert tty is not None
    fd = stream.fileno()
    original = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = stream.read(1)
        if first == "\x1b":
            second = stream.read(1)
            if second != "[":
                return first
            third = stream.read(1)
            return f"{first}{second}{third}"
        return first
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def _confirm_overwrite(prompt: str) -> bool:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    response = sys.stdin.readline().strip().lower()
    return response in {"y", "yes"}


if __name__ == "__main__":
    raise SystemExit(main())
