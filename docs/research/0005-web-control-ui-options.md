# 0005: Web Control UI Options

Date: 2026-06-09

## Scope

This note records the initial tradeoff discussion around a phone-accessible Control Room UI so the repo can resume that work later without re-litigating the same first-pass questions.

Current desired scope:

- fastest possible prototype
- mostly one operator
- LAN-only access
- limited polish
- stay mostly in Python

This is explicitly not a multi-user/auth/product-surface design exercise yet.

## Current Recommendation

If the next step is "get Control Room onto a phone quickly," `NiceGUI` is the leading candidate.

Why:

- it keeps almost all implementation in Python
- it already provides a browser UI plus realtime server/client updates
- it fits the current prototype scope better than building and maintaining a separate JavaScript app

If the project later decides the web UI is becoming a long-lived primary surface, re-evaluate a cleaner server/client split then. That future concern is out of current scope.

## NiceGUI Suitability

NiceGUI appears suitable for the intended interaction model:

- live status panels
- live log streaming
- command dispatch
- cancel actions
- replay controls

Its built-in realtime channel means we would not start by designing our own raw WebSocket layer if we pick NiceGUI. NiceGUI already handles browser/server synchronization internally.

## iPhone Safari / HTTP Caveat

There is a repo-specific caveat for the current NiceGUI line on iPhone Safari.

Relevant finding:

- NiceGUI issue `#5802` reports that on iOS Safari with NiceGUI `3.7.1`, a minimal app served over plain `http://<LAN-IP>:<port>` reloads repeatedly instead of staying connected.
- The issue report attributes this to the client handshake using `crypto.randomUUID()` in a context that iOS Safari treats as insecure for LAN HTTP.
- The report also states that older NiceGUI versions (`2.9.0` and `2.23.3`) worked on the same device/setup.

Source:

- <https://github.com/zauberzeug/nicegui/issues/5802>

Working interpretation:

- this is a real risk for a NiceGUI-on-iPhone-over-LAN prototype
- the problem is not "Safari cannot display HTTP pages"
- the problem is "NiceGUI v3 currently appears to depend on a browser capability that fails in this insecure-context path on iOS Safari"

## What This Means For Other Stacks

This does not automatically mean every custom web stack would fail the same way.

More precise conclusion:

- plain HTTP plus normal browser traffic is still allowed on iPhone Safari
- a custom stack using basic HTTP requests plus plain WebSocket traffic would not necessarily reproduce the NiceGUI bug
- the failure class appears when the framework or app depends on secure-context-only browser APIs while running from plain `http://<LAN-IP>`

So:

- this is partly an iOS Safari / WebKit secure-context issue
- but the exact repeated-reload failure is still framework-specific unless our own frontend makes the same kind of API choice

## Practical Decision Point

If we prototype with NiceGUI and want iPhone Safari support, plan on HTTPS rather than assuming plain LAN HTTP is enough.

If we build a tiny custom frontend instead, plain HTTP plus WebSocket may still work for the current scope, but HTTPS remains the safer long-term default once mobile Safari is in the loop.

## Deferred Implementation Shape

Before any web UI is added, the likely minimum internal refactor is:

1. separate Control Room state/actions from the current Textual rendering layer
2. keep the control logic reusable from either Textual or web UI
3. add the web UI as a thin surface over that shared logic

That is the smallest change that preserves the current app while enabling a phone UI.
