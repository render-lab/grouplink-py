"""Read both Notion databases and build each profile's page model.

Shared so the workflow and the preview script query and order the rows the same way.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from render import TaskContext
from render_lab_tasks_notion.query_database import query_database
from render_lab_tasks_notion.types import PageDTO

from grouplink.config import RebuildConfig
from grouplink.links import (
    LINK_SORTS,
    ProfilePage,
    ProfileRow,
    assert_default_slug,
    group_by_profile,
    section_ranks,
    servable_profiles,
    to_link_rows,
    to_profile_rows,
    visible_rows,
)
from grouplink.notion_schema import read_select_options


@dataclass(frozen=True)
class NotionSite:
    """What one read of the two Notion databases gives the rebuild and the preview."""

    #: The raw link rows, which the skip report reads.
    link_pages: list[PageDTO]
    profiles: list[ProfileRow]
    #: One page per profile whose slug the web service can serve. Each page holds
    #: its visible rows, in `page_order`.
    pages: list[ProfilePage]


async def read_notion_site(ctx: TaskContext, cfg: RebuildConfig) -> NotionSite:
    """Three runs in parallel.

    A link's `Profiles` relation holds the Notion page ids of its Profiles rows, which
    is how the two join. Notion sorts the links by `Order`. The profiles need no sort.
    The tabs are in the order of the `Section` options in the links database schema.
    """
    link_pages, profile_pages, section_options = await asyncio.gather(
        ctx.run(
            query_database,
            {"databaseId": cfg.database_id, "sorts": LINK_SORTS, "limit": cfg.limit},
        ),
        ctx.run(query_database, {"databaseId": cfg.profiles_database_id, "limit": cfg.limit}),
        ctx.run(read_select_options, {"databaseId": cfg.database_id, "property": "Section"}),
    )

    profiles = to_profile_rows(profile_pages)
    servable = servable_profiles(profiles)
    assert_default_slug(servable, cfg.default_slug)
    pages = group_by_profile(
        visible_rows(to_link_rows(link_pages)), servable, section_ranks(section_options)
    )

    return NotionSite(link_pages=link_pages, profiles=profiles, pages=pages)
