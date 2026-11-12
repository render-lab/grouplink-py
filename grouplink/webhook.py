"""Entry point for grouplink-webhook-py, the web service that serves the page and
receives Notion's webhook.

It serves each profile's page from the snapshot grouplink.rebuild writes to Key
Value, and it is the only thing that starts a rebuild.

render-lab-triggers can mount webhook adapters, but an adapter's `map()` result is
dispatched immediately, so the debounce cannot live inside one. This uses the package
for the dispatcher and the task route, and handles the rest itself.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import uvicorn
from redis.asyncio import Redis
from render_lab_triggers import create_dispatch_server, render_dispatcher
from render_lab_triggers.types import Json, RunOutcome, StartedRun, WorkflowDispatcher
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from grouplink.config import env_int
from grouplink.logs import configure as configure_logging
from grouplink.notion_webhook import (
    DEFAULT_DEBOUNCE_MS,
    NotionWebhook,
    WebhookRequest,
)
from grouplink.page import sections
from grouplink.site_store import SiteStore
from grouplink.snapshot import SITE_KEY

log = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# render.com proxies /links/* here and removes /links, so the pages ask for
# /links/assets/ and this service gets /assets/. A direct visit to the
# onrender.com URL asks for /links/assets/, so the service serves both paths.
ASSET_PATHS = ("/assets", "/links/assets")
FONT_PATHS = tuple(f"{path}/fonts/" for path in ASSET_PATHS)


#: The page routes after "/". The pages use the same two prefixes as the assets.
PAGE_PATHS = (
    "/links",
    "/links/",
    "/links/{slug}",
    "/links/{slug}/",
    "/links/{slug}/{section}",
    "/links/{slug}/{section}/",
    "/{slug}",
    "/{slug}/",
    "/{slug}/{section}",
    "/{slug}/{section}/",
)

NOT_FOUND_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    "<title>Not found</title></head>"
    '<body><p>There is no page here. <a href="/">Go to the links page</a>.</p></body></html>'
)

#: Largest Notion webhook body the service reads. The same limit as the
#: render-lab-triggers task route.
MAX_BODY_BYTES = 1_048_576

#: Seconds a client waits before it asks again while there is no site to serve.
RETRY_AFTER_SECONDS = 60


class ResponseHeaders:
    """Security headers on every response, plus a one-year cache on the fonts.

    The page sets the rest of its Content-Security-Policy in a meta tag. A meta tag
    cannot set frame-ancestors, so that one directive is a header.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
                headers["Content-Security-Policy"] = "frame-ancestors 'none'"
                headers["X-Frame-Options"] = "DENY"
                if message["status"] == 200 and scope["path"].startswith(FONT_PATHS):
                    headers["Cache-Control"] = "public, max-age=31536000, immutable"
            await send(message)

        await self._app(scope, receive, send_with_headers)


class RedactedDispatcher:
    """Log a dispatch error, and give the dispatch server a general error in its place.

    The dispatch server puts the error text in its 502 response. That text can hold a
    Render API error body, so the caller gets only a general message.
    """

    def __init__(self, dispatcher: WorkflowDispatcher) -> None:
        self._dispatcher = dispatcher

    async def start(self, task: str, args: list[Json]) -> StartedRun:
        try:
            return await self._dispatcher.start(task, args)
        except Exception as error:
            log.exception("dispatch of %s failed", task)
            raise RuntimeError("see the web service log") from error

    async def run(self, task: str, args: list[Json], timeout_ms: float) -> RunOutcome:
        try:
            return await self._dispatcher.run(task, args, timeout_ms)
        except Exception as error:
            log.exception("dispatch of %s failed", task)
            raise RuntimeError("see the web service log") from error


class OnlyTask:
    """Pass a POST /tasks/:task request to the dispatch server only for one task.

    The Workflow registers more tasks than the rebuild, such as the Key Value `set`
    task. The dispatch server starts any of them, so this route answers 404 for the rest.
    """

    def __init__(self, task: str, app: ASGIApp) -> None:
        self._task = task
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["path_params"]["task"] != self._task:
            await JSONResponse({"error": "not found"}, status_code=404)(scope, receive, send)
            return
        await self._app(scope, receive, send)


def create_app(
    *,
    workflow_slug: str,
    dispatcher: WorkflowDispatcher,
    webhook: NotionWebhook,
    store: SiteStore,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
) -> Starlette:
    """POST /tasks/:task comes from render-lab-triggers. It is how you force a
    rebuild or run a dry run with custom input from the command line. Passing the
    dispatcher in means every route starts runs through the same client.
    """
    # The library types the ASGI scope as `dict`, so mypy does not accept the server as
    # an ASGIApp. The server works with any ASGI scope.
    dispatch_server = cast(
        ASGIApp,
        create_dispatch_server(
            workflow_slug=workflow_slug, dispatcher=RedactedDispatcher(dispatcher)
        ),
    )

    async def page(request: Request) -> Response:
        # Slugs and section slugs are lowercase, so /Shifra/AI-Agents goes to
        # /shifra/ai-agents.
        path = request.url.path
        if path != path.lower():
            return _redirect(request, path.lower())

        snapshot = await store.snapshot()
        if snapshot is None:
            return PlainTextResponse(
                "The page is being built. Try again in a minute.",
                status_code=503,
                headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
            )

        slug = request.path_params.get("slug", snapshot.default_slug)
        section = request.path_params.get("section")
        model = snapshot.pages.get(slug)
        # The first tab has one URL, the profile path, so /shifra/<first tab> goes to
        # /shifra.
        if section is not None and model is not None and sections(model)[0].slug == section:
            return _redirect(request, path.rstrip("/").rsplit("/", 1)[0])
        rendered = store.page(snapshot, slug, section)
        if rendered is None:
            return HTMLResponse(NOT_FOUND_HTML, status_code=404)

        # no-cache makes the browser revalidate, which the ETag makes cheap.
        headers = {"ETag": rendered.etag, "Cache-Control": "no-cache"}
        if _etag_matches(request.headers.get("if-none-match", ""), rendered.etag):
            return Response(status_code=304, headers=headers)
        return HTMLResponse(rendered.html, headers=headers)

    async def healthz(_request: Request) -> Response:
        return PlainTextResponse("ok")

    async def notion(request: Request) -> Response:
        body = await _read_body(request, MAX_BODY_BYTES)
        if body is None:
            return JSONResponse({"error": "payload too large"}, status_code=413)
        result = webhook.handle(
            WebhookRequest(
                headers={key.lower(): value for key, value in request.headers.items()},
                raw_body=body.decode("utf-8", errors="replace"),
            )
        )
        if result.body is None:
            return Response(status_code=result.status)
        return JSONResponse(result.body, status_code=result.status)

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        yield
        # Render stops the old instance on every deploy. Start the waiting run now,
        # or the edit that scheduled it is lost.
        await webhook.flush()
        if on_shutdown is not None:
            await on_shutdown()

    return Starlette(
        routes=[
            Route("/", page, methods=["GET"]),
            Route("/healthz", healthz, methods=["GET"]),
            Route("/tasks/{task}", OnlyTask(webhook.task, dispatch_server), methods=["POST"]),
            Route("/webhooks/notion", notion, methods=["POST"]),
            *(Mount(path, StaticFiles(directory=ASSETS_DIR)) for path in ASSET_PATHS),
            # `links` is a reserved slug, so no profile can shadow the /links routes.
            *(Route(path, page, methods=["GET"]) for path in PAGE_PATHS),
        ],
        middleware=[Middleware(ResponseHeaders)],
        lifespan=lifespan,
    )


def _relative_url(path: str, target: str) -> str:
    """A relative URL from `path` to `target`.

    The URL is relative because render.com removes the `/links` prefix before the
    request gets here. A relative URL keeps the prefix that the browser shows. It goes
    up only to the first segment that changes.
    """
    segments = path.split("/")
    target_segments = target.split("/")
    first = next(
        (i for i, (a, b) in enumerate(zip(segments, target_segments, strict=False)) if a != b),
        min(len(segments), len(target_segments)),
    )
    first = min(first, len(segments) - 1, len(target_segments) - 1)
    return "../" * (len(segments) - 1 - first) + "/".join(target_segments[first:])


def _redirect(request: Request, target: str) -> Response:
    location = _relative_url(request.url.path, target)
    if request.url.query:
        location += "?" + request.url.query
    return RedirectResponse(location, status_code=301)


async def _read_body(request: Request, limit: int) -> bytes | None:
    """The request body, or None when it is longer than `limit` bytes."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _etag_matches(if_none_match: str, etag: str) -> bool:
    candidates = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
    return etag in candidates or "*" in candidates


def build_app() -> Starlette:
    workflow_slug = os.environ.get("WORKFLOW_SLUG")
    if not workflow_slug:
        raise ValueError("set WORKFLOW_SLUG to the Workflow service's slug")
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise ValueError("set REDIS_URL to the grouplink-cache Key Value connection string")

    # Short timeouts, because a request waits on this read. The store serves its
    # last good copy when the read fails.
    redis = Redis.from_url(
        redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
    )
    task = os.environ.get("REBUILD_TASK", "grouplink.rebuild")
    dispatcher = render_dispatcher(slug=workflow_slug)

    async def read_site() -> str | None:
        value: str | None = await redis.get(SITE_KEY)
        return value

    return create_app(
        workflow_slug=workflow_slug,
        dispatcher=dispatcher,
        webhook=NotionWebhook(
            dispatch=dispatcher.start,
            task=task,
            secret=os.environ.get("NOTION_WEBHOOK_SECRET"),
            debounce_ms=env_int(os.environ, "DEBOUNCE_MS", DEFAULT_DEBOUNCE_MS),
        ),
        store=SiteStore(read=read_site, rebuild=lambda: dispatcher.start(task, [{}])),
        on_shutdown=redis.aclose,
    )


def main() -> None:
    configure_logging()
    port = env_int(os.environ, "PORT", 3000)
    log.info("grouplink-webhook-py listening on %s", port)
    uvicorn.run(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
