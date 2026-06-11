from __future__ import annotations

from edap.control_room.models import CommandHelp


CONTROL_ROOM_COMMANDS: list[CommandHelp] = [
    CommandHelp(
        name="dock",
        usage="dock",
        summary="Dock at the current station target and auto-refuel plus auto-repair after touchdown.",
        detail="Starts the docking routine. If you're already in normal space it skips the supercruise-exit wait; otherwise it waits for the drop, sends the docking request menu flow, then auto-refuels and attempts one repair press after docking before returning to station services. Prefix the command with ! to bypass the configured control-room start delay for that launch only.",
    ),
    CommandHelp(
        name="undock",
        usage="undock",
        summary="Launch from the current station and wait until the ship is clear of the station.",
        detail="Runs the station launch menu flow, waits for the Undocked journal event, then waits for the NoTrack music event that confirms the ship has cleared the station before reporting success.",
    ),
    CommandHelp(
        name="jump",
        usage="jump",
        summary="Trigger the FSD jump sequence and zero throttle on arrival.",
        detail="Sends the hyperspace control, waits for the jump to start, waits to re-enter supercruise at the destination, then sets speed to zero.",
    ),
    CommandHelp(
        name="escape",
        usage="escape",
        summary="Set speed full and boost away until the FSD mass-lock clears.",
        detail="Sets throttle to 100%, then checks Status.json in a loop: if the FSD mass-locked flag is set, fires a boost and waits the configured boost delay before checking again. Stops and reports success once the flag clears or is absent.",
    ),
    CommandHelp(
        name="boost",
        usage="boost",
        summary="Fire boost three times immediately.",
        detail="Sends the ship's boost binding three times in a row without checking mass-lock state. Use escape instead when you want the Status.json mass-lock check loop.",
    ),
    CommandHelp(
        name="buy",
        usage="buy <item> [amount|max]",
        summary="Buy a commodity from the current station market.",
        detail="Opens the commodities market, finds the named item in the buy list, sets the requested quantity or MAX, confirms the trade, and waits for a MarketBuy journal event.",
    ),
    CommandHelp(
        name="sell",
        usage="sell [item] [amount|max]",
        summary="Sell cargo from the current station market.",
        detail="With an item name it sells that commodity. With no item it walks your cargo manifest and tries to sell every non-stolen, non-mission cargo item, skipping items the market won't buy.",
    ),
    CommandHelp(
        name="haul",
        usage="haul [commodity]",
        summary="Run the two-station haul loop, prompting for both stations and both cargo legs.",
        detail="Starts a symmetric loop: at station 1 it sells the cargo bought at station 2, then buys station 1's outbound cargo; at station 2 it does the reverse. Control room prompts for both station names, both systems, both outbound cargo names, the galaxy-map settle delay, and the docking timeout.",
    ),
    CommandHelp(
        name="multi_leg_haul",
        usage="multi_leg_haul <route.json | spansh-url>",
        summary="Run a standalone multi-leg haul route from our JSON schema or a Spansh result.",
        detail="Loads a generalized multi-leg haul definition, then resumes from live journal/cargo/market state rather than persisted session state. Use this for finite multi-hop trading routes that buy and sell the exact commodity list on each leg.",
        aliases=("mult",),
    ),
    CommandHelp(
        name="dest",
        usage="dest <system>",
        summary="Open the galaxy map and plot a route to a named system.",
        detail="Opens the galaxy map, types the destination into search, plots the route, verifies NavRoute.json, and closes the map again. Control room also prompts for the galaxy-map settle delay, with Enter accepting the configured default.",
        aliases=("set_dest",),
    ),
    CommandHelp(
        name="market",
        usage="market | market clear | market filter <name> | market lock | market unlock",
        summary="Control the market panel filter and lock state.",
        detail="Use 'market filter <name>' to filter visible items, 'market' or 'market clear' to remove the filter, 'market lock' to freeze the panel to the current station, and 'market unlock' to resume live updates.",
    ),
    CommandHelp(
        name="verbose",
        usage="verbose [on|off]",
        summary="Turn verbose keypress logging on or off.",
        detail="When verbose mode is on, individual key presses from routine dispatch are written into the activity log. When off, only higher-level progress messages are shown.",
    ),
    CommandHelp(
        name="instant",
        usage="instant [on|off]",
        summary="Toggle the control-room command launch delay off or on.",
        detail="With no argument it toggles instant mode. When instant mode is on, executable commands launch immediately without the configured control-room start delay until you turn it off again. The ! prefix still works for one-off immediate launches.",
    ),
    CommandHelp(
        name="commands",
        usage="commands",
        summary="List every supported control-room command.",
        detail="Prints the command names and their one-line summaries so you can discover what control room currently supports.",
    ),
    CommandHelp(
        name="help",
        usage="help [command]",
        summary="Show general help or explain one command in plain English.",
        detail="With no argument it explains how to discover commands. With a command name, it prints that command's usage, aliases, and what it is meant to do in human terms.",
        aliases=("?",),
    ),
    CommandHelp(
        name="replay",
        usage="replay",
        summary="Open the replay history browser for execute-or-edit replay.",
        detail="Shows recent saved commands across sessions in the activity-pane replay browser. Press Enter to execute the selected entry with its normal delay behavior, press ! to execute it immediately without adding a ! to the saved command, press e to reopen it for editing, or press * on a haul entry to save or clear it as the default haul setup.",
        aliases=("history",),
    ),
    CommandHelp(
        name="quit",
        usage="q | quit | exit",
        summary="Cancel active work if needed, then shut down control room cleanly.",
        detail="Starts the control-room shutdown path. If a routine is running, control room cancels it first and exits after the worker unwinds; otherwise it exits immediately.",
        aliases=("q", "exit"),
    ),
]

CONTROL_ROOM_COMMAND_INDEX: dict[str, CommandHelp] = {}
for command in CONTROL_ROOM_COMMANDS:
    CONTROL_ROOM_COMMAND_INDEX[command.name] = command
    for alias in command.aliases:
        CONTROL_ROOM_COMMAND_INDEX[alias] = command
