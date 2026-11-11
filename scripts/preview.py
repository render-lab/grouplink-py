"""Build the snapshot from the real Notion databases and write it to a local Redis,
so a local web service serves the same pages as production.

Run with `uv run python -m scripts.preview`.

This is the read half of grouplink.rebuild: Notion, with no health check.
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from render_lab_test_utils import local_ctx

import grouplink.notion_relation  # noqa: F401  (imported for its side effect)
from grouplink.config import load_config
from grouplink.links import to_card
from grouplink.page import PageModel
from grouplink.read_notion import read_notion_site
from scripts.local_site import REPO_ROOT, write_snapshot


async def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    ctx = local_ctx()
    cfg = load_config({"dryRun": True})

    pages = (await read_notion_site(ctx, cfg)).pages
    write_snapshot(
        {
            page.profile.slug: PageModel(
                name=page.profile.name,
                tagline=page.profile.tagline,
                cards=[to_card(row) for row in page.rows],
            )
            for page in pages
        },
        cfg.default_slug,
    )


if __name__ == "__main__":
    asyncio.run(main())
