"""Tiny in-process domain event bus. Modules publish events; other modules subscribe.

Handlers run synchronously after the publisher's work, inside the same request. Handlers that
need durability (notifications, webhooks) enqueue to the background queue instead of doing I/O.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

log = logging.getLogger("talvynza.events")
_handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)


def subscribe(event: str, handler: Callable[[dict[str, Any]], None]) -> None:
    if handler not in _handlers[event]:
        _handlers[event].append(handler)


def publish(event: str, payload: dict[str, Any]) -> None:
    for h in _handlers.get(event, []):
        try:
            h(payload)
        except Exception:  # a failing subscriber must not break the publisher
            log.exception("event handler failed", extra={"event": event})


def clear() -> None:  # tests
    _handlers.clear()
