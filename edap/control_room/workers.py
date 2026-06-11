from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from rich.markup import escape
from textual.worker import get_current_worker

from edap.control_room import error_text
from edap.control_room.failure_messages import describe_routine_exception, describe_routine_failure
from edap.progress_controls import ProgressShipControls
from edap.state import JournalWatcher


class RoutineCancelled(Exception):
    """Raised when a control-room routine worker is cancelled."""


class PendingRoutineCancelled(RoutineCancelled):
    """Raised when a delayed command is cancelled before execution begins."""


class CancellationProxy:
    def __init__(self, target: Any, check_cancelled: Callable[[], None]) -> None:
        self._target = target
        self._check_cancelled = check_cancelled

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self._check_cancelled()
            return attr(*args, **kwargs)

        return wrapped


class WorkerHost(Protocol):
    _config: Any
    _controls: Any
    _journal_dir: Any
    _verbose_controls: bool
    _routine_worker: Any | None
    _routine_active: bool
    _active_routine_name: str | None
    _shutdown_requested: bool

    def _log(self, msg: str) -> None: ...
    def _handle_event(self, ev: dict[str, Any]) -> None: ...
    def _load_market_json(self) -> None: ...
    def _sync_status_snapshot(self) -> None: ...
    def _refresh_haul_stats(self) -> None: ...
    def _stop_haul_stats(self) -> None: ...
    def _clear_pending_haul_stop(self) -> None: ...
    def _make_sleeper(self) -> Callable[[float], None]: ...
    def _run_in_thread(self, fn: Callable[[], Any]) -> Any: ...
    def _finalize_shutdown(self) -> None: ...
    def call_from_thread(self, callback: Callable[..., Any], *args: Any) -> None: ...


def start_watcher_loop(app: WorkerHost) -> None:
    worker = get_current_worker()
    watcher = JournalWatcher(app._journal_dir)
    refresh_interval_s = app._config.control_room.status_refresh_seconds
    last_market_check = 0.0
    while not worker.is_cancelled:
        try:
            for ev in watcher.poll():
                app.call_from_thread(app._handle_event, ev)
            now = time.monotonic()
            if now - last_market_check > refresh_interval_s:
                app.call_from_thread(app._sync_status_snapshot)
                app.call_from_thread(app._load_market_json)
                app.call_from_thread(app._refresh_haul_stats)
                last_market_check = now
        except Exception:
            time.sleep(1.0)


def check_routine_ready(app: WorkerHost) -> bool:
    if app._controls is None:
        app._log(f"[red]{escape(error_text.render(app._config, 'controls_unavailable'))}[/]")
        return False
    if app._routine_active:
        app._log("[yellow]A routine is already running — wait for it to finish[/]")
        return False
    return True


def raise_if_worker_cancelled() -> None:
    worker = get_current_worker()
    if worker.is_cancelled:
        raise RoutineCancelled()


def make_progress(app: WorkerHost) -> Callable[[str], None]:
    def progress(msg: str) -> None:
        raise_if_worker_cancelled()
        app.call_from_thread(app._log, f"[dim]  {escape(msg)}[/]")

    return progress


def make_controls(app: WorkerHost, progress_fn: Callable[[str], None]) -> ProgressShipControls:
    controls = ProgressShipControls(app._controls, progress_fn, verbose=app._verbose_controls)
    return CancellationProxy(controls, raise_if_worker_cancelled)


def make_watcher(app: WorkerHost) -> Any:
    watcher = JournalWatcher(app._journal_dir)
    return CancellationProxy(watcher, raise_if_worker_cancelled)


def make_sleeper() -> Callable[[float], None]:
    def sleeper(delay_s: float) -> None:
        deadline = time.monotonic() + max(0.0, delay_s)
        while True:
            raise_if_worker_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.1, remaining))

    return sleeper


def start_delayed_routine(
    app: WorkerHost,
    *,
    description: str,
    start_message: str,
    fn: Callable[[], Any],
    skip_delay: bool = False,
    active_routine_name: str | None = None,
    on_start: Callable[[], None] | None = None,
) -> None:
    delay_s = 0.0 if (skip_delay or app._instant_mode) else app._config.control_room.command_delay_seconds

    def run_with_optional_delay() -> Any:
        if delay_s > 0:
            try:
                app._make_sleeper()(delay_s)
            except RoutineCancelled as exc:
                raise PendingRoutineCancelled(
                    f"Cancelled pending {description} before execution."
                ) from exc
        if on_start is None:
            app.call_from_thread(app._log, start_message)
        else:
            app.call_from_thread(on_start)
        return fn()

    app._routine_active = True
    app._active_routine_name = active_routine_name
    if delay_s > 0:
        app._log(f"[dim]Executing {escape(description)} in {delay_s:.1f}s...[/]")
    app._routine_worker = app._run_in_thread(run_with_optional_delay)


def run_routine_thread(
    app: WorkerHost,
    fn: Callable[[], Any],
) -> None:
    worker = get_current_worker()
    try:
        result = fn()
        if worker.is_cancelled:
            app.call_from_thread(app._log, "[yellow]Routine cancelled.[/]")
        elif result is not None:
            status = result.dispatch.status
            if status == "ok":
                app.call_from_thread(
                    app._log,
                    f"[green]Done: {escape(result.action)} ({escape(status)})[/]",
                )
            else:
                message, suggestion = describe_routine_failure(result, app._config)
                app.call_from_thread(
                    app._log,
                    f"[red]Failed: {escape(result.action)} -- {escape(message)}[/]",
                )
                if suggestion:
                    app.call_from_thread(
                        app._log,
                        f"[yellow]Try: {escape(suggestion)}[/]",
                    )
    except PendingRoutineCancelled as exc:
        app.call_from_thread(app._log, f"[yellow]{escape(str(exc))}[/]")
    except RoutineCancelled:
        app.call_from_thread(app._log, "[yellow]Routine cancelled.[/]")
    except Exception as exc:
        message, suggestion = describe_routine_exception(exc, app._config)
        app.call_from_thread(app._log, f"[red]{escape(message)}[/]")
        if suggestion:
            app.call_from_thread(app._log, f"[yellow]Try: {escape(suggestion)}[/]")
    finally:
        app.call_from_thread(clear_routine, app)


def clear_routine(app: WorkerHost) -> None:
    app._routine_active = False
    app._routine_worker = None
    if app._active_routine_name in {"haul", "multi_leg_haul"}:
        app._stop_haul_stats()
        app._clear_pending_haul_stop()
    app._active_routine_name = None
    if app._shutdown_requested:
        app._finalize_shutdown()
