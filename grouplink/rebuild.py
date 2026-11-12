"""grouplink.rebuild — read the profiles and their links from Notion, health-check
the links, write the site to Key Value for the web service to serve, and log the outcome.

Every `await ctx.run(...)` below is a separate durable run on its own instance, with
that package's retry policy, tracked in the dashboard. The health check fans out
in batches of BATCH_SIZE, so the run opens at most that many checks at a time.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypedDict

from render import TaskContext
from render.client.errors import TaskRunError
from render_lab_tasks_http.request import request
from render_lab_tasks_http.types import RequestResult
from render_lab_tasks_notion.types import PageDTO
from render_lab_tasks_render_kv.get import get as kv_get
from render_lab_tasks_render_kv.set import set as kv_set

from grouplink.app import app
from grouplink.config import RebuildInput, load_config
from grouplink.icons import DEFAULT_ICON
from grouplink.links import (
    ProfileRow,
    SkippedRow,
    fetchable_urls,
    skipped_rows,
    to_page_model,
    unique_urls,
    unknown_icons,
    unservable_profiles,
)
from grouplink.read_notion import read_notion_site
from grouplink.snapshot import SITE_KEY, build_snapshot, parse_snapshot

log = logging.getLogger(__name__)


#: Statuses that mean the URL resolved but refused an unadorned GET. X answers 403 and
#: LinkedIn answers 999 for a request with no browser fingerprint, so neither is dead.
REFUSED_STATUSES = {401, 403, 405, 429, 999}

#: Without a cap, a 100-row database opens 100 concurrent runs and hits every
#: linked site at once.
BATCH_SIZE = 10


class SkippedRowDTO(TypedDict):
    title: str
    url: str
    reason: str


class RebuildResult(TypedDict):
    #: Profiles in the snapshot.
    pageCount: int
    #: Distinct card URLs across every page.
    linkCount: int
    #: Link rows read from Notion that render on no page, and why.
    skipped: list[SkippedRowDTO]
    deadLinks: list[str]
    #: sha256 of the snapshot's pages and default slug.
    hash: str
    #: Whether the run wrote a new snapshot to Key Value.
    published: bool
    siteUrl: str
    dryRun: bool


@app.task(name="grouplink.rebuild")
async def rebuild(ctx: TaskContext, input: RebuildInput | None = None) -> RebuildResult:
    cfg = load_config(input)

    # 1) Parallel fan-out: read both databases and the Section options.
    site = await read_notion_site(ctx, cfg)
    pages = site.pages

    skipped = _report_notion_problems(site.link_pages, site.profiles)

    # A link on three pages is one URL to health-check. A mailto: card renders from
    # its Notion row alone, so it is a card URL but not a web URL and skips stage 2.
    rows = [row for page in pages for row in page.rows]
    card_urls = unique_urls(rows)
    web_urls = fetchable_urls(card_urls)

    # 2) Batched fan-out: health-check every link. tasks-http has no HEAD method, so
    #    this is a GET whose body we discard.
    checks = await _map_in_batches(web_urls, lambda url: _check(ctx, url))
    dead_links = [
        f"{url} ({check['status'] if check else 'no response'})"
        for url, check in zip(web_urls, checks, strict=True)
        if _unreachable(check)
    ]

    # 3) Build the snapshot the web service serves: every profile's page model and
    #    the slug the root page shows.
    models = {page.profile.slug: to_page_model(page) for page in pages}
    snapshot = build_snapshot(models, cfg.default_slug, datetime.now(UTC))
    snapshot_hash = parse_snapshot(snapshot).hash

    result: RebuildResult = {
        "pageCount": len(pages),
        "linkCount": len(card_urls),
        "skipped": [_to_skipped_dto(row) for row in skipped],
        "deadLinks": dead_links,
        "hash": snapshot_hash,
        "published": False,
        "siteUrl": cfg.site_url,
        "dryRun": cfg.dry_run,
    }

    # Dry-run lives here in the caller, not in the packs.
    if cfg.dry_run:
        return result

    # 4) Chained runs: read the published snapshot, and write the new one only when
    #    its hash differs. One SET, so a reader never sees half of a rebuild. No TTL,
    #    so Key Value never evicts it. The page is live when the SET returns.
    current = await ctx.run(kv_get, {"key": SITE_KEY})
    if _snapshot_hash(current.get("value")) == snapshot_hash:
        if dead_links:
            _log_outcome("grouplink is unchanged, but some links are unreachable.", dead_links)
        return result

    await ctx.run(kv_set, {"key": SITE_KEY, "value": snapshot})
    result["published"] = True

    _log_outcome(
        f"grouplink is live with {len(card_urls)} links across {len(pages)} pages. {cfg.site_url}",
        dead_links,
    )
    return result


async def _map_in_batches[T, R](items: list[T], fn: Callable[[T], Awaitable[R]]) -> list[R]:
    """asyncio.gather in batches of BATCH_SIZE, in input order."""
    results: list[R] = []
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        results.extend(await asyncio.gather(*(fn(item) for item in batch)))
    return results


async def _check(ctx: TaskContext, url: str) -> RequestResult | None:
    """The GET's status, or None when the request fails after its retries. The http
    pack raises on any status of 500 or more, which includes LinkedIn's 999."""
    try:
        return await ctx.run(request, {"method": "GET", "url": url})
    except TaskRunError as error:
        log.warning("health check failed for %s: %s", url, error)
        return None


def _report_notion_problems(
    link_pages: list[PageDTO], profiles: list[ProfileRow]
) -> list[SkippedRow]:
    """Logs what you can see in Notion but the site does not show: a row that
    reaches no page, and an Icon option no file matches. Both are otherwise silent.
    Returns the skipped rows, which the run reports as part of its result.
    """
    skipped = skipped_rows(link_pages, profiles) + unservable_profiles(profiles)
    for row in skipped:
        log.info('skipped "%s": %s', row.title, row.reason)
    for name in unknown_icons(link_pages):
        log.info('unknown Icon "%s", using %s', name, DEFAULT_ICON)
    return skipped


def _unreachable(check: RequestResult | None) -> bool:
    if check is None:
        return True
    return not check["ok"] and int(check["status"]) not in REFUSED_STATUSES


def _snapshot_hash(value: str | None) -> str | None:
    """The hash of the published snapshot. None when there is none this build can read."""
    if not value:
        return None
    try:
        return parse_snapshot(value).hash
    except ValueError:
        return None


def _to_skipped_dto(row: SkippedRow) -> SkippedRowDTO:
    return {"title": row.title, "url": row.url, "reason": row.reason}


def _log_outcome(text: str, dead_links: list[str]) -> None:
    body = f"{text}\nUnreachable: {', '.join(dead_links)}" if dead_links else text
    log.info(body)
