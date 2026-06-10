from __future__ import annotations

from typing import Callable

ProgressCallback = Callable[[str], None]
AnnouncementCallback = Callable[..., None]


def noop_progress(_: str) -> None:
    pass


def noop_announce(*_args: object, **_kwargs: object) -> None:
    pass
