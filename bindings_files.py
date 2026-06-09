from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edap.bindings_inventory import (
    DEFAULT_BACKUP_DIR,
    choose_bindings_file,
    copy_bindings_to_backup,
    list_bindings_files,
)
from edap.config import ConfigError, DEFAULT_CONFIG_PATH
from edap.runtime import build_runtime_context, load_config_with_fallback


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List detected Elite Dangerous .binds files and copy them into a gitignored backup folder"
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


if __name__ == "__main__":
    raise SystemExit(main())
