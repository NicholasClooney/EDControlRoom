"""Static TUI viewer for the user's Elite Dangerous keyboard bindings.

Renders the curated ``REQUIRED_BINDINGS`` scope as colored, grouped panels via
``rich``. Mirrors the ``--config`` / ``--bindings-file`` surface of
``check_bindings.py`` so users can switch between the JSON output and the
glanceable layout without learning new flags.
"""

from __future__ import annotations

import argparse
import sys
from math import ceil
from pathlib import Path
from xml.etree.ElementTree import parse as parse_xml

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from edap.binding_groups import BindingGroup, BindingRow, group_bindings
from edap.binding_lookup import load_binding_lookup
from edap.bindings import REQUIRED_BINDINGS
from edap.config import ConfigError, DEFAULT_CONFIG_PATH
from edap.runtime import build_runtime_context, load_config_with_fallback


TOP_ROW_TITLES = ("Roll & Throttle", "Pitch & Yaw")
BOTTOM_TITLE = "Unmapped"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Static colored viewer for the curated Elite Dangerous keyboard bindings",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config TOML file",
    )
    parser.add_argument(
        "--bindings-file",
        default=None,
        help="Optional bindings file path that bypasses config loading",
    )
    args = parser.parse_args()

    bindings_file = _resolve_bindings_file(args)
    if bindings_file is None:
        return 2

    try:
        lookup = load_binding_lookup(bindings_file, actions=REQUIRED_BINDINGS)
    except Exception as exc:
        sys.stderr.write(f"Could not load bindings from {bindings_file}: {exc}\n")
        return 2

    preset = _read_root_attributes(bindings_file)
    groups = group_bindings(lookup.supported_actions(), lookup.issues())

    console = Console()
    console.print(_render_header(bindings_file, preset))
    console.print()

    top_panels = [
        _render_group_panel(g, two_column_items=False)
        for g in groups
        if g.title in TOP_ROW_TITLES
    ]
    if top_panels:
        console.print(Columns(top_panels, equal=True, expand=True))

    for group in groups:
        if group.title in TOP_ROW_TITLES or group.title == BOTTOM_TITLE:
            continue
        console.print(_render_group_panel(group))

    bottom_group = next((g for g in groups if g.title == BOTTOM_TITLE), None)
    if bottom_group is not None and bottom_group.rows:
        console.print(_render_group_panel(bottom_group, two_column_items=False))

    return 0 if not any(g.is_unmapped for g in groups) else 1


def _resolve_bindings_file(args: argparse.Namespace) -> Path | None:
    if args.bindings_file:
        path = Path(args.bindings_file)
        if not path.is_file():
            sys.stderr.write(f"Bindings file does not exist or is not a file: {path}\n")
            return None
        return path

    try:
        loaded = load_config_with_fallback(args.config)
    except FileNotFoundError:
        sys.stderr.write(
            f"Config file not found: {args.config}\n"
            f"Create `config.toml` from `config.example.toml`, or pass `--config /path/to/config.toml`.\n"
        )
        return None
    except ConfigError as exc:
        sys.stderr.write(f"Invalid config: {exc}\n")
        return None

    runtime = build_runtime_context(loaded.config)
    bindings_file = runtime.bindings.effective_path
    if bindings_file is None:
        bindings_source = runtime.bindings.cli_source_status()
        sys.stderr.write(
            "Could not resolve bindings file. "
            f"Source status: {bindings_source}. Configure `paths.bindings_file` or ensure CrossOver auto-detection works.\n"
        )
        return None
    return bindings_file


def _read_root_attributes(bindings_file: Path) -> dict[str, str]:
    try:
        root = parse_xml(bindings_file).getroot()
    except Exception:
        return {}
    return {
        "PresetName": root.attrib.get("PresetName", ""),
        "MajorVersion": root.attrib.get("MajorVersion", ""),
        "MinorVersion": root.attrib.get("MinorVersion", ""),
    }


def _render_header(bindings_file: Path, preset: dict[str, str]) -> Text:
    header = Text()
    header.append("Bindings file: ", style="bold")
    header.append(str(bindings_file), style="cyan")
    header.append("\n")
    preset_name = preset.get("PresetName") or "?"
    major = preset.get("MajorVersion") or "?"
    minor = preset.get("MinorVersion") or "?"
    header.append("Preset: ", style="bold")
    header.append(preset_name, style="magenta")
    header.append("  Version: ", style="bold")
    header.append(f"{major}.{minor}", style="magenta")
    return header


def _render_group_panel(group: BindingGroup, two_column_items: bool = True) -> Panel:
    if not group.rows:
        body = Table.grid(padding=(0, 2))
        body.add_column(justify="right")
        body.add_column(justify="left", no_wrap=False)
        body.add_column(justify="left")
        body.add_row(Text("(empty)", style="dim"), Text(""), Text(""))
    elif not two_column_items or len(group.rows) <= 1:
        body = _build_rows_table(group.rows)
    else:
        split = ceil(len(group.rows) / 2)
        left_table = _build_rows_table(group.rows[:split])
        right_table = _build_rows_table(group.rows[split:])
        body = Columns([left_table, right_table], equal=True, expand=True)

    border_style = "red" if group.is_unmapped else "green"
    title_style = "bold red" if group.is_unmapped else "bold green"
    return Panel(
        body,
        title=Text(group.title, style=title_style),
        border_style=border_style,
        title_align="left",
    )


def _build_rows_table(rows: list[BindingRow]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right")
    table.add_column(justify="left", no_wrap=False)
    table.add_column(justify="left")
    for row in rows:
        table.add_row(*_render_row_cells(row))
    return table


def _render_row_cells(row: BindingRow) -> tuple[Text, Text, Text]:
    if row.is_ok:
        action_text = Text(row.action, style="dim white")
        arrow = Text("->", style="dim")
        binding_text = _render_key_combo(row.key or "", row.modifier)
        return action_text, arrow, binding_text

    action_text = Text(row.action, style="red")
    arrow = Text("->", style="dim red")
    reason = row.reason or row.status
    binding_text = Text(f"({row.status}: {reason})", style="red")
    return action_text, arrow, binding_text


def _render_key_combo(key: str, modifier: str | None) -> Text:
    combo = Text()
    if modifier:
        combo.append(_pretty_token(modifier), style="magenta")
        combo.append("+", style="magenta")
    combo.append(_pretty_token(key), style="bold cyan")
    return combo


def _pretty_token(token: str) -> str:
    """Display normalized binding tokens in a friendlier ``Ctrl+X`` form."""

    aliases = {
        "left_shift": "Shift",
        "right_shift": "Shift",
        "left_control": "Ctrl",
        "right_control": "Ctrl",
        "left_alt": "Alt",
        "right_alt": "Alt",
        "space": "Space",
        "enter": "Enter",
        "tab": "Tab",
        "escape": "Esc",
        "backspace": "Backspace",
        "delete": "Delete",
        "page_up": "PageUp",
        "page_down": "PageDown",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "home": "Home",
        "end": "End",
    }
    if token in aliases:
        return aliases[token]
    if token.startswith("numpad_"):
        return f"NumPad{token[7:]}"
    if len(token) == 1:
        return token.upper()
    if token.startswith("f") and token[1:].isdigit():
        return token.upper()
    return token


if __name__ == "__main__":
    raise SystemExit(main())
