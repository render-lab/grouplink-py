"""Signs a webhook body the way Notion does, for tests that send signed events."""

from __future__ import annotations

import hashlib
import hmac


def sign(raw_body: str, secret: str) -> str:
    """The X-Notion-Signature value for `raw_body`."""
    digest = hmac.new(secret.encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    return f"sha256={digest}"
