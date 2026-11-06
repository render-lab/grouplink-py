"""A task that reads the options of a select property from a Notion database schema.

The Notion pack has no task that reads a schema, so this one uses the pack's client
for the auth headers and the API version.
"""

from __future__ import annotations

from typing import TypedDict

from render import TaskContext, Workflows
from render_lab_tasks_core.http import enc
from render_lab_tasks_notion.client import Client, Deps, dependencies
from render_lab_tasks_notion.retry import NOTION_RETRY

app = Workflows()


class SelectOptionsInput(TypedDict):
    databaseId: str
    property: str


async def read_select_options_impl(
    ctx: TaskContext, input: SelectOptionsInput, *, deps: Deps | None = None
) -> list[str]:
    """The option names of the select property, in the order Notion shows them.

    A property that is missing or is not a select has no options. Raises ValueError
    when the database has no data source.
    """
    async with dependencies(deps) as resolved:
        notion = resolved.notion
        if not isinstance(notion, Client):
            raise TypeError("read_select_options needs the Notion pack's HTTP client")

        database = await notion.api.call("/databases/" + enc(input["databaseId"]))
        sources = database.get("data_sources") or []
        if not sources or not sources[0].get("id"):
            raise ValueError(f'Database "{input["databaseId"]}" has no data sources.')
        source = await notion.api.call("/data_sources/" + enc(sources[0]["id"]))

    name = input["property"]
    prop = (source.get("properties") or {}).get(name)
    if not prop or prop.get("type") != "select":
        return []
    return [str(option["name"]) for option in prop["select"]["options"]]


@app.task(name="grouplink.readSelectOptions", retry=NOTION_RETRY)
async def read_select_options(ctx: TaskContext, input: SelectOptionsInput) -> list[str]:
    return await read_select_options_impl(ctx, input)
