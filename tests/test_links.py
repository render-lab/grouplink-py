from __future__ import annotations

from typing import Any

import pytest
from render_lab_tasks_notion.types import PageDTO

from grouplink.links import (
    assert_default_slug,
    favicon_url,
    fetchable_urls,
    group_by_profile,
    meta_cache_key,
    page_order,
    section_ranks,
    servable_profiles,
    skipped_rows,
    to_card,
    to_icon_name,
    to_link_rows,
    to_profile_rows,
    unique_urls,
    unknown_icons,
    unservable_profiles,
    visible_rows,
)


def page(props: dict[str, Any], title: str, id: str = "p") -> PageDTO:
    return {
        "id": id,
        "url": "https://www.notion.so/p",
        "title": title,
        "properties": props,
        "createdTime": "",
        "lastEditedTime": "",
    }


PAGES = [
    page({"URL": "https://b.example", "Visible": True}, "B"),
    page({"URL": "https://a.example", "Visible": True}, "A"),
    page({"URL": "https://hidden.example", "Visible": False}, "Hidden"),
    page({"URL": "https://x.com/render", "Visible": True}, "X"),
    page({"URL": "", "Visible": True}, "No URL"),
]

PROFILES = [
    page({"Slug": "shifra", "Tagline": "DevRel"}, "Shifra", id="profile-shifra"),
    page({"Slug": "Alex", "Tagline": ""}, "Alex", id="profile-alex"),
]


class TestToLinkRows:
    def test_reads_the_url_property_not_the_notion_page_url(self) -> None:
        assert to_link_rows(PAGES)[0].url == "https://b.example"

    def test_skips_rows_with_no_url(self) -> None:
        assert "No URL" not in [row.title for row in to_link_rows(PAGES)]

    @pytest.mark.parametrize(
        "url",
        ["ftp://example.com", "mailto:", "javascript:alert(1)", "https://a b/"],
    )
    def test_skips_a_url_the_site_cannot_link_to(self, url: str) -> None:
        assert to_link_rows([page({"URL": url}, "Bad")]) == []

    @pytest.mark.parametrize(
        "url",
        ["https://render.com", "mailto:shifra@render.com"],
    )
    def test_keeps_an_http_or_mailto_url(self, url: str) -> None:
        assert [row.url for row in to_link_rows([page({"URL": url}, "Good")])] == [url]

    @pytest.mark.parametrize(
        ("cell", "expected"),
        [
            ("http://render.com", "https://render.com"),
            ("render.com/careers", "https://render.com/careers"),
        ],
    )
    def test_reads_a_row_as_https(self, cell: str, expected: str) -> None:
        assert [row.url for row in to_link_rows([page({"URL": cell}, "Good")])] == [expected]

    def test_keeps_the_notion_order_and_drops_hidden_rows(self) -> None:
        assert [row.title for row in visible_rows(to_link_rows(PAGES))] == ["B", "A", "X"]

    def test_falls_back_to_the_title_property(self) -> None:
        rows = to_link_rows([page({"URL": "https://a.example", "Title": " Named "}, "")])
        assert rows[0].title == "Named"

    def test_reads_the_icon_column(self) -> None:
        rows = to_link_rows([page({"URL": "https://a.example", "Icon": "Workflows"}, "A")])
        assert rows[0].icon == "workflows"

    def test_defaults_the_icon_when_the_column_is_missing(self) -> None:
        assert to_link_rows([page({"URL": "https://a.example"}, "A")])[0].icon == "arrow"

    def test_reads_the_section_column(self) -> None:
        rows = to_link_rows(
            [
                page({"URL": "https://a.example", "Section": " AI Agents "}, "A"),
                page({"URL": "https://b.example"}, "B"),
            ]
        )
        assert [row.section for row in rows] == ["AI Agents", ""]


class TestOrder:
    def test_reads_a_number_as_order_and_anything_else_as_none(self) -> None:
        rows = to_link_rows(
            [
                page({"URL": "https://a.example", "Order": 10}, "A"),
                page({"URL": "https://b.example", "Order": 2.5}, "B"),
                page({"URL": "https://c.example", "Order": 0}, "C"),
                page({"URL": "https://d.example", "Order": None}, "D"),
                page({"URL": "https://e.example", "Order": "10"}, "E"),
                page({"URL": "https://f.example", "Order": True}, "F"),
                page({"URL": "https://g.example"}, "G"),
            ]
        )
        assert [row.order for row in rows] == [10, 2.5, 0, None, None, None, None]


def ordered(*cells: tuple[str, str, float | None], options: list[str] | None = None) -> list[str]:
    """Titles in `page_order`, for rows given as (title, section, order).

    The options default to the sections in the order the rows first give them.
    """
    rows = to_link_rows(
        [
            page({"URL": f"https://{title}.example", "Section": section, "Order": order}, title)
            for title, section, order in cells
        ]
    )
    if options is None:
        options = [section for _, section, _ in cells]
    return [row.title for row in page_order(rows, section_ranks(options))]


class TestPageOrder:
    def test_puts_the_tabs_in_option_order(self) -> None:
        assert ordered(
            ("agents-1", "AI Agents", 1),
            ("startups-2", "Startups", 2),
            ("workflows-3", "Workflows", 3),
            options=["Workflows", "AI Agents", "Startups"],
        ) == ["workflows-3", "agents-1", "startups-2"]

    def test_puts_a_section_with_no_option_after_the_others(self) -> None:
        assert ordered(
            ("new-1", "New", 1),
            ("agents-2", "AI Agents", 2),
            options=["AI Agents"],
        ) == ["agents-2", "new-1"]

    def test_puts_each_tab_in_order(self) -> None:
        assert ordered(
            ("agents-20", "AI Agents", 20),
            ("agents-5", "AI Agents", 5),
            ("startups-1", "Startups", 1),
        ) == ["agents-5", "agents-20", "startups-1"]

    def test_puts_rows_with_no_section_last_by_order(self) -> None:
        assert ordered(
            ("loose-10", "", 10),
            ("agents-20", "AI Agents", 20),
            ("loose-5", "", 5),
            ("new-1", "New", 1),
            options=["AI Agents"],
        ) == ["agents-20", "new-1", "loose-5", "loose-10"]

    def test_puts_rows_with_no_section_in_a_misc_option_by_its_rank(self) -> None:
        assert ordered(
            ("agents-1", "AI Agents", 1),
            ("loose-2", "", 2),
            ("misc-3", "Misc", 3),
            options=["Misc", "AI Agents"],
        ) == ["loose-2", "misc-3", "agents-1"]

    def test_moves_rows_with_no_order_to_the_end_of_their_tab(self) -> None:
        assert ordered(
            ("agents-empty", "AI Agents", None),
            ("agents-5", "AI Agents", 5),
            ("startups-empty", "Startups", None),
            ("startups-1", "Startups", 1),
        ) == ["agents-5", "agents-empty", "startups-1", "startups-empty"]

    def test_keeps_input_order_with_no_sections(self) -> None:
        assert ordered(("b", "", 2), ("empty", "", None), ("a", "", 1)) == ["a", "b", "empty"]

    def test_ranks_options_with_one_slug_as_one_tab(self) -> None:
        assert section_ranks(["Startups", "AI Agents", "startups", "!!"]) == {
            "startups": 0,
            "ai-agents": 1,
        }

    def test_uses_the_ranks_of_every_row_for_one_page(self) -> None:
        rows = to_link_rows(
            [
                page({"URL": "https://a.example", "Section": "Startups"}, "A"),
                page({"URL": "https://b.example", "Section": "AI Agents"}, "B"),
                page({"URL": "https://c.example", "Section": "Startups"}, "C"),
            ]
        )
        ranks = {"ai-agents": 0, "startups": 1}
        assert [row.title for row in page_order(rows, ranks)] == ["B", "A", "C"]


class TestToIconName:
    @pytest.mark.parametrize("value", ["workflows", " Workflows ", "WORKFLOWS"])
    def test_strips_and_lowercases_a_known_option(self, value: str) -> None:
        assert to_icon_name(value) == "workflows"

    @pytest.mark.parametrize("value", ["", "   ", "nonesuch", None, 7, ["arrow"]])
    def test_falls_back_for_an_empty_unknown_or_non_string_cell(self, value: Any) -> None:
        assert to_icon_name(value) == "arrow"


class TestUnknownIcons:
    def test_names_the_options_no_file_matches_in_first_seen_order(self) -> None:
        pages = [
            page({"URL": "https://a.example", "Icon": "Sparkle"}, "A"),
            page({"URL": "https://b.example", "Icon": "workflows"}, "B"),
            page({"URL": "https://c.example", "Icon": "Rocket"}, "C"),
            page({"URL": "https://d.example", "Icon": "sparkle"}, "D"),
            page({"URL": "https://e.example"}, "E"),
        ]
        assert unknown_icons(pages) == ["sparkle", "rocket"]


class TestToProfileRows:
    def test_lowercases_the_slug(self) -> None:
        assert [profile.slug for profile in to_profile_rows(PROFILES)] == ["shifra", "alex"]

    def test_skips_a_row_with_no_slug(self) -> None:
        assert to_profile_rows([page({"Tagline": "x"}, "Nameless")]) == []


class TestGroupByProfile:
    profiles = to_profile_rows(PROFILES)
    rows = to_link_rows(
        [
            page({"URL": "https://shared.example", "Profiles": ["profile-shifra"]}, "Shifra only"),
            page({"URL": "https://all.example", "Everyone": True}, "Everyone"),
            page(
                {"URL": "https://both.example", "Everyone": True, "Profiles": ["profile-shifra"]},
                "Everyone and related",
            ),
            page({"URL": "https://orphan.example"}, "Related to nobody"),
        ]
    )

    def titles_for(self, slug: str) -> list[str]:
        grouped = group_by_profile(self.rows, self.profiles, {})
        return [row.title for p in grouped if p.profile.slug == slug for row in p.rows]

    def test_puts_an_everyone_row_on_every_page(self) -> None:
        assert self.titles_for("alex") == ["Everyone", "Everyone and related"]

    def test_counts_a_row_that_is_both_everyone_and_related_once(self) -> None:
        assert self.titles_for("shifra") == [
            "Shifra only",
            "Everyone",
            "Everyone and related",
        ]

    def test_renders_a_row_related_to_nobody_nowhere(self) -> None:
        assert "Related to nobody" not in self.titles_for("shifra")
        assert "Related to nobody" not in self.titles_for("alex")


class TestSkippedRows:
    def test_names_the_check_each_row_failed(self) -> None:
        profiles = to_profile_rows(PROFILES)
        pages = [
            page({"URL": "https://ok.example", "Profiles": ["profile-shifra"]}, "Fine"),
            page({"URL": "", "Profiles": ["profile-shifra"]}, "No URL"),
            page({"URL": "https://x.example"}, ""),
            page({"URL": "https://h.example", "Visible": False, "Everyone": True}, "Hidden"),
            page({"URL": "https://o.example"}, "Orphan"),
            page({"URL": "https://g.example", "Profiles": ["profile-ghost"]}, "Ghost"),
            page({"URL": "ftp://example.com", "Profiles": ["profile-shifra"]}, "FTP"),
            page({"URL": "javascript:alert(1)", "Profiles": ["profile-shifra"]}, "Script"),
            page({"URL": "mailto:shifra@render.com", "Profiles": ["profile-shifra"]}, "Email"),
        ]
        assert [(row.title, row.reason) for row in skipped_rows(pages, profiles)] == [
            ("No URL", "no URL"),
            ("https://x.example", "no Title"),
            ("Hidden", "Visible is unchecked"),
            ("Orphan", "no Profiles relation and Everyone is unchecked"),
            ("Ghost", "its Profiles relation points at no row in the Profiles database"),
            ("FTP", "URL is not an http, https, or mailto: link"),
            ("Script", "URL is not an http, https, or mailto: link"),
        ]


class TestUniqueUrls:
    def test_keeps_first_seen_order(self) -> None:
        rows = to_link_rows(
            [
                page({"URL": "https://b.example"}, "B"),
                page({"URL": "https://a.example"}, "A"),
                page({"URL": "https://b.example"}, "B again"),
            ]
        )
        assert unique_urls(rows) == ["https://b.example", "https://a.example"]


class TestFetchableUrls:
    def test_keeps_only_the_urls_with_a_page_to_fetch(self) -> None:
        urls = ["https://render.com", "mailto:shifra@render.com", "http://render.com"]
        assert fetchable_urls(urls) == ["https://render.com", "http://render.com"]


class TestFaviconUrl:
    def test_points_at_the_origin_root(self) -> None:
        assert favicon_url("https://render.com/tutorials/x") == "https://render.com/favicon.ico"

    def test_returns_empty_for_a_url_that_will_not_parse(self) -> None:
        assert favicon_url("not a url") == ""

    def test_returns_empty_for_a_mailto_link(self) -> None:
        assert favicon_url("mailto:shifra@render.com") == ""


class TestAssertDefaultSlug:
    def test_passes_when_a_profile_has_the_slug(self) -> None:
        assert_default_slug(to_profile_rows(PROFILES), "shifra")

    def test_names_the_slug_that_matches_nobody(self) -> None:
        with pytest.raises(ValueError, match="SITE_DEFAULT_SLUG"):
            assert_default_slug(to_profile_rows(PROFILES), "nobody")

    def test_names_a_reserved_slug_as_reserved(self) -> None:
        with pytest.raises(ValueError, match='SITE_DEFAULT_SLUG "assets" is reserved'):
            assert_default_slug(to_profile_rows(PROFILES), "assets")


class TestServableProfiles:
    MIXED = to_profile_rows(
        [
            *PROFILES,
            page({"Slug": "tasks"}, "Tasks", id="profile-tasks"),
            page({"Slug": "a/b"}, "Slash", id="profile-slash"),
            page({"Slug": "Shifra"}, "Second Shifra", id="profile-shifra-2"),
        ]
    )

    def test_keeps_the_first_profile_with_each_servable_slug(self) -> None:
        assert [p.id for p in servable_profiles(self.MIXED)] == [
            "profile-shifra",
            "profile-alex",
        ]

    def test_names_why_each_other_profile_gets_no_page(self) -> None:
        assert [(row.title, row.reason) for row in unservable_profiles(self.MIXED)] == [
            ("Tasks", 'Slug "tasks" is reserved for the web service'),
            ("Slash", 'Slug "a/b" contains "/"'),
            ("Second Shifra", 'Slug "shifra" is already used by another profile'),
        ]


def test_meta_cache_key_is_versioned() -> None:
    assert meta_cache_key("https://a.example") == "gl:meta:v1:https://a.example"


def test_to_card_keeps_the_section() -> None:
    row = to_link_rows([page({"URL": "https://a.example", "Section": "Startups"}, "A")])[0]
    assert to_card(row, "").section == "Startups"
