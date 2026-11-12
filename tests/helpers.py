"""Fakes and helpers that more than one test module uses."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any


def sign(raw_body: str, secret: str) -> str:
    """The X-Notion-Signature value for `raw_body`."""
    digest = hmac.new(secret.encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class Dispatcher:
    """Records each run it is asked to start, and starts nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any]]] = []

    async def start(self, task: str, args: list[Any]) -> dict[str, str]:
        self.calls.append((task, args))
        return {"runId": "run-1"}
