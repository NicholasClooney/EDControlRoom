from __future__ import annotations

from edap.config import AppConfig


def template(config: AppConfig, key: str) -> str:
    value = config.error_messages.templates.get(key)
    if value is not None:
        return value
    return key.replace("_", " ")


def render(config: AppConfig, key: str, /, **values: object) -> str:
    text = template(config, key)
    try:
        return text.format(**values)
    except Exception:
        return text
