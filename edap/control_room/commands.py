"""Command dispatch and the simple, no-routine commands."""
from __future__ import annotations

from rich.markup import escape

from edap.control_room.help import CONTROL_ROOM_COMMAND_INDEX, CONTROL_ROOM_COMMANDS
from edap.control_room.history import now_iso
from edap.control_room.interfaces import CommandHost
from edap.control_room_state import CommandHistoryEntry

def dispatch(app: CommandHost, raw: str, *, skip_delay_override: bool | None = None) -> None:
    app._log(f"[dim]Command: {escape(raw)}[/]")
    skip_delay = False
    command_raw = raw
    if command_raw.startswith("!"):
        skip_delay = True
        command_raw = command_raw[1:].lstrip()
        if not command_raw:
            app._log("[dim]Unknown command: ![/]")
            return
    if skip_delay_override is not None:
        skip_delay = skip_delay_override

    cmd = command_raw.lower()
    if cmd in {"q", "quit", "exit"}:
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="quit", timestamp=now_iso()))
        app._request_shutdown("quit command")
        return

    parts = cmd.split(None, 1)
    verb = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""
    raw_parts = command_raw.split(None, 1)
    raw_rest = raw_parts[1].strip() if len(raw_parts) > 1 else ""

    if verb == "dock":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="dock", timestamp=now_iso()))
        app._cmd_dock(skip_delay=skip_delay)
    elif verb == "undock":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="undock", timestamp=now_iso()))
        app._cmd_undock(skip_delay=skip_delay)
    elif verb == "jump":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="jump", timestamp=now_iso()))
        app._cmd_jump(skip_delay=skip_delay)
    elif verb == "escape":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="escape", timestamp=now_iso()))
        app._cmd_escape(skip_delay=skip_delay)
    elif verb == "boost":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="boost", timestamp=now_iso()))
        app._cmd_boost(skip_delay=skip_delay)
    elif verb == "buy":
        app._cmd_buy(raw_rest, skip_delay=skip_delay)
    elif verb == "sell":
        app._cmd_sell(raw_rest, skip_delay=skip_delay)
    elif verb == "haul":
        app._cmd_haul(raw_rest, skip_delay=skip_delay, raw_command=raw)
    elif verb in {"dest", "set_dest"}:
        if not raw_rest:
            app._log("[red]Usage: dest <system name>[/]")
        else:
            app._cmd_dest(raw_rest, skip_delay=skip_delay, raw_command=raw)
    elif verb == "market":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="market", params={"value": raw_rest}, timestamp=now_iso()))
        cmd_market(app, raw_rest)
    elif verb == "verbose":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="verbose", params={"value": rest}, timestamp=now_iso()))
        cmd_verbose(app, rest)
    elif verb == "commands":
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="commands", timestamp=now_iso()))
        cmd_commands(app)
    elif verb in {"help", "?"}:
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="help", params={"topic": raw_rest}, timestamp=now_iso()))
        cmd_help(app, raw_rest)
    elif verb in {"replay", "history"}:
        app._record_history_entry(CommandHistoryEntry(raw=raw, command="replay", timestamp=now_iso()))
        cmd_resume(app)
    elif verb == "reload":
        app._cmd_reload()
    else:
        app._log(f"[dim]Unknown command: {escape(raw)}[/]")


def cmd_commands(app: CommandHost) -> None:
    app._log("[dim]Supported commands:[/]")
    for command in CONTROL_ROOM_COMMANDS:
        aliases = f" [dim](aliases: {', '.join(command.aliases)})[/]" if command.aliases else ""
        app._log(f"[bold]{escape(command.usage)}[/] — {escape(command.summary)}{aliases}")


def cmd_resume(app: CommandHost) -> None:
    app._show_resume_picker()


def cmd_help(app: CommandHost, rest: str) -> None:
    topic = rest.strip().lower()
    if not topic:
        app._log("[dim]Use [bold]commands[/] to list everything, or [bold]help <command>[/] for one command in plain English.[/]")
        return

    command = CONTROL_ROOM_COMMAND_INDEX.get(topic)
    if command is None:
        app._log(f"[red]Unknown help topic: {escape(rest)}[/]")
        return

    aliases = f"  Aliases: {', '.join(command.aliases)}" if command.aliases else ""
    app._log(
        f"[bold]{escape(command.name)}[/] — {escape(command.usage)}"
        f"{f'[dim]{escape(aliases)}[/]' if aliases else ''}"
    )
    app._log(escape(command.detail))


def cmd_verbose(app: CommandHost, rest: str) -> None:
    if rest in {"on", "1", "true"}:
        app._verbose_controls = True
        app._log("[dim]Verbose key logging on — key presses will appear in the activity log.[/]")
    elif rest in {"off", "0", "false", ""}:
        app._verbose_controls = False
        app._log("[dim]Verbose key logging off.[/]")
    else:
        state = "on" if app._verbose_controls else "off"
        app._log(f"[dim]verbose {state}  —  use: verbose on | verbose off[/]")


def cmd_market(app: CommandHost, rest: str) -> None:
    rest_lower = rest.lower()
    if rest_lower == "lock":
        app._market.locked = True
        app._log("[dim]Market panel locked.[/]")
        app._refresh_market()
    elif rest_lower == "unlock":
        app._market.locked = False
        app._log("[dim]Market panel unlocked.[/]")
        app._load_market_json()
        app._refresh_market()
    elif rest_lower.startswith("filter "):
        term = rest[7:].strip()
        if not term:
            app._log("[red]Usage: market filter <item name>[/]")
            return
        app._market_filter = term.title()
        app._log(f"[dim]Market filter: {escape(app._market_filter)}[/]")
        app._refresh_market()
    else:
        app._market_filter = None
        app._log("[dim]Market filter cleared.[/]")
        app._refresh_market()
