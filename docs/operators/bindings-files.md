# Bindings Files Utility

`bindings_files.py` is a small operator utility for inspecting, backing up, restoring, and replacing Elite Dangerous `.binds` files.

It works against the currently detected active bindings file unless you pass `--bindings-file`.

## Commands

List detected `.binds` files in the live Frontier bindings folder:

```sh
uv run python3 bindings_files.py
```

Back up the newest detected file into the repo-local gitignored backup folder:

```sh
uv run python3 bindings_files.py backup
```

Back up a specific detected file by number or filename:

```sh
uv run python3 bindings_files.py backup 2
uv run python3 bindings_files.py backup Custom.4.2.binds
```

Restore a backup onto the active bindings file:

```sh
uv run python3 bindings_files.py restore
uv run python3 bindings_files.py restore 3
uv run python3 bindings_files.py restore Custom.4.2-2026-06-09.binds
```

Notes:

- `restore` saves a fresh backup of the current active bindings file before overwriting it
- interactive restore supports up/down selection, typed prefix filtering, numeric selection, `Backspace`, `Ctrl-C`, and `q`

Apply a shipped default preset over the active custom bindings file:

```sh
uv run python3 bindings_files.py apply-default
uv run python3 bindings_files.py apply-default 1
uv run python3 bindings_files.py apply-default ControlPad.binds
```

Notes:

- `apply-default` prompts before overwriting the active file
- it saves a fresh backup first if you confirm
- it preserves the active file's `PresetName` / version metadata so the result still behaves like the current custom profile
- this path is not yet live-validated against a real Elite session; if it does not behave as expected, please open an issue or report the exact command and resulting file state

## Selection Behavior

For `restore` and `apply-default`:

- type a number and press `Enter` to pick an entry directly
- type a prefix to filter the visible list
- use up/down and `Enter` to select from the filtered list
- use `Backspace` to remove characters from the current filter
- use `Ctrl-C` or `q` to cancel without changing files

## Safety Model

- `backup` copies files into `backup/bindings/` by default
- `restore` always backs up the current active bindings file before replacing it
- `apply-default` always backs up the current active bindings file before replacing it after confirmation

## Related Docs

- [../research/0006-elite-bindings-preset-locations.md](../research/0006-elite-bindings-preset-locations.md)
- [../diagnostics/bindings-reference.md](../diagnostics/bindings-reference.md)
