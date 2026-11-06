from __future__ import annotations

from typing import Any

import httpx
import pytest
from render_lab_tasks_notion.client import Client, Deps

from grouplink.notion_schema import read_select_options_impl

ENV = {"NOTION_TOKEN": "notion-token"}


async def read(properties: dict[str, Any], sources: list[dict[str, Any]] | None = None) -> Any:
    """The options of `Section`, from a fake Notion with one data source."""

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/databases/db_links":
            data_sources = [{"id": "ds-1"}] if sources is None else sources
            return httpx.Response(200, json={"data_sources": data_sources})
        if request.url.path == "/v1/data_sources/ds-1":
            return httpx.Response(200, json={"properties": properties})
        raise AssertionError(f"no fake for {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as http:
        return await read_select_options_impl(
            None,
            {"databaseId": "db_links", "property": "Section"},
            deps=Deps(notion=Client(http, env=ENV)),
        )


async def test_returns_the_options_in_notion_order() -> None:
    options = [{"name": "Workflows"}, {"name": "AI Agents"}, {"name": "Startups"}]
    section = {"type": "select", "select": {"options": options}}
    assert await read({"Section": section}) == ["Workflows", "AI Agents", "Startups"]


async def test_returns_no_options_when_the_property_is_missing() -> None:
    assert await read({"Order": {"type": "number", "number": {}}}) == []


async def test_returns_no_options_when_the_property_is_not_a_select() -> None:
    assert await read({"Section": {"type": "rich_text", "rich_text": {}}}) == []


async def test_refuses_a_database_with_no_data_source() -> None:
    with pytest.raises(ValueError, match="no data sources"):
        await read({}, sources=[])
