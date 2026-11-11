"""Write a seed snapshot to a local Redis, from seed links written out by hand.

It lets you run the web service locally without Notion. The golden page tests
render the same seed links. Run with `uv run python -m scripts.placeholder`.
"""

from __future__ import annotations

from dataclasses import dataclass

from grouplink.icons import IconName
from grouplink.links import to_card
from grouplink.page import PageModel
from scripts.local_site import write_snapshot


@dataclass(frozen=True)
class SeedLink:
    title: str
    url: str
    icon: IconName
    section: str = ""


@dataclass(frozen=True)
class SeedProfile:
    name: str
    slug: str
    links: list[SeedLink]


SHARED = [
    SeedLink(
        title="Funded founder? Apply to the Render startup program",
        url="https://render.com/startups",
        icon="form",
    ),
    SeedLink(
        title="Render website",
        url="https://render.com/",
        icon="render",
    ),
]

PROFILES = [
    SeedProfile(
        name="Shifra",
        slug="shifra",
        links=[
            *SHARED,
            SeedLink(
                title="Get started with Render Workflows",
                url="https://render.com/tutorials/render-workflows",
                icon="workflows",
            ),
        ],
    ),
    SeedProfile(
        name="Graham",
        slug="graham",
        links=[
            SeedLink(
                title="Create your Render account",
                url="https://dashboard.render.com/register",
                icon="one",
            ),
            SeedLink(
                title="Deploy your first service",
                url="https://render.com/docs/your-first-deploy",
                icon="two",
            ),
            SeedLink(
                title="Add a custom domain",
                url="https://render.com/docs/custom-domains",
                icon="three",
            ),
            *SHARED,
            SeedLink(
                title="Render docs",
                url="https://render.com/docs",
                icon="info",
            ),
        ],
    ),
]

DEFAULT_SLUG = "shifra"
TAGLINE = "The fastest path to production for full-stack applications and agents"


def main() -> None:
    write_snapshot(
        {
            profile.slug: PageModel(
                name=profile.name,
                tagline=TAGLINE,
                cards=[to_card(link) for link in profile.links],
            )
            for profile in PROFILES
        },
        DEFAULT_SLUG,
    )


if __name__ == "__main__":
    main()
