from __future__ import annotations

import pytest

from grouplink.jsurl import gmail_compose_url, normalize_url


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        ("cell", "expected"),
        [
            ("http://render.com/", "https://render.com/"),
            ("HTTP://render.com/", "https://render.com/"),
            ("https://render.com/", "https://render.com/"),
            ("HTTPS://render.com/", "https://render.com/"),
            ("render.com", "https://render.com"),
            ("render.com/careers", "https://render.com/careers"),
            ("render.com:8080/x", "https://render.com:8080/x"),
            ("  render.com  ", "https://render.com"),
            ("ren\tder.com", "https://render.com"),
            ("mailto:shifra@render.com", "mailto:shifra@render.com"),
            ("MAILTO:shifra@render.com", "mailto:shifra@render.com"),
            ("mailto:", "mailto:"),
            ("ftp://example.com/f", "ftp://example.com/f"),
            ("javascript:alert(1)", "javascript:alert(1)"),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_normalizes_a_notion_cell(self, cell: str, expected: str) -> None:
        assert normalize_url(cell) == expected

    def test_upgrades_http_without_touching_the_rest_of_the_url(self) -> None:
        cell = "http://user@render.com:8080/a/b?q=1#f"
        assert normalize_url(cell) == "https://user@render.com:8080/a/b?q=1#f"

    def test_is_idempotent(self) -> None:
        for cell in ["render.com", "http://render.com", "mailto:a@b.com", "ftp://x.com"]:
            once = normalize_url(cell)
            assert normalize_url(once) == once


GMAIL = "https://mail.google.com/mail/?view=cm&fs=1"


class TestGmailComposeUrl:
    @pytest.mark.parametrize(
        ("mailto", "expected"),
        [
            ("mailto:shifra@render.com", f"{GMAIL}&to=shifra@render.com"),
            ("MAILTO:shifra@render.com", f"{GMAIL}&to=shifra@render.com"),
            ("mailto:a@b.com,c@d.com", f"{GMAIL}&to=a@b.com,c@d.com"),
            (
                "mailto:a@b.com?subject=Hi%20there&body=Line%201%0ALine%202",
                f"{GMAIL}&to=a@b.com&su=Hi%20there&body=Line%201%0ALine%202",
            ),
            ("mailto:a@b.com?cc=c@d.com&bcc=e@f.com", f"{GMAIL}&to=a@b.com&cc=c@d.com&bcc=e@f.com"),
            ("mailto:a@b.com?Subject=Hi&BODY=Yo", f"{GMAIL}&to=a@b.com&su=Hi&body=Yo"),
            ("mailto:a@b.com?in-reply-to=x&subject=Hi", f"{GMAIL}&to=a@b.com&su=Hi"),
            ("mailto:?subject=Hi", f"{GMAIL}&su=Hi"),
            ("mailto:?to=a@b.com&subject=Hi", f"{GMAIL}&to=a@b.com&su=Hi"),
            ("mailto:a@b.com?To=c@d.com", f"{GMAIL}&to=a@b.com,c@d.com"),
        ],
    )
    def test_maps_a_mailto_url_to_gmail_compose(self, mailto: str, expected: str) -> None:
        assert gmail_compose_url(mailto) == expected

    def test_encodes_a_plus_sign_so_gmail_does_not_read_it_as_a_space(self) -> None:
        url = gmail_compose_url("mailto:shifra+links@render.com?subject=C++")
        assert url == f"{GMAIL}&to=shifra%2Blinks@render.com&su=C%2B%2B"

    @pytest.mark.parametrize(
        ("mailto", "expected"),
        [
            ("mailto:a@b.com?subject=Hello world", f"{GMAIL}&to=a@b.com&su=Hello%20world"),
            ("mailto:a@b.com?subject=Hi#x&body=Yo", f"{GMAIL}&to=a@b.com&su=Hi%23x&body=Yo"),
            ("mailto:a&b@x.com", f"{GMAIL}&to=a%26b@x.com"),
            ("mailto:a@b.com?subject=Q%26A", f"{GMAIL}&to=a@b.com&su=Q%26A"),
            ("mailto:a@b.com?subject=caf%C3%A9", f"{GMAIL}&to=a@b.com&su=caf%C3%A9"),
        ],
    )
    def test_reencodes_each_value_for_the_query_string(self, mailto: str, expected: str) -> None:
        assert gmail_compose_url(mailto) == expected
