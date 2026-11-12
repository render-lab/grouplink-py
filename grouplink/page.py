"""The whole page. One function, one string, no framework and no build step —
the web service serves whatever this returns for each profile.

The look comes from the Website Lab redesign of the links page: color tokens in
:root with a dark override, PP Neue Montreal for all text, 1px hairlines, and
purple only for the focus ring.

The page carries its own Content-Security-Policy, with the inline style and
script blocks allowed by hash. The browser blocks any inline style or script
that is not in STYLES, THEME_SCRIPT, or PAGE_SCRIPT. The policy is a meta tag
rather than a response header so the hashes cannot drift from the content
they cover.

The module is page.py rather than render.py, because `render` is the SDK's
import name.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from grouplink.icons import ICON_NAMES, ORDINALS, SVG_ICONS, IconName
from grouplink.jsurl import gmail_compose_url, is_mailto_url, normalize_mailto
from grouplink.jsurl import parse as parse_url


@dataclass(frozen=True)
class LinkCard:
    """One row of the links list."""

    #: Display text, from Notion.
    title: str
    #: Final href, exactly as the Notion row gives it.
    url: str
    #: Which file under grouplink/assets/link-icons the card draws in its left column.
    #: The names `one`, `two`, and `three` have no file. They draw a numbered box.
    icon: IconName
    #: The `Section` cell, which names the card's tab. Empty puts it in the Misc tab.
    section: str = ""


@dataclass(frozen=True)
class SocialLink:
    label: str
    url: str


@dataclass(frozen=True)
class PageModel:
    name: str
    #: The meta tags hold it on every page. The intro shows it on all pages but the
    #: default one.
    tagline: str
    cards: list[LinkCard] = field(default_factory=list)


@dataclass(frozen=True)
class Section:
    """One tab of a page and the cards it shows."""

    title: str
    #: The last segment of the tab's path. Empty only on a page with no sections.
    slug: str
    cards: list[LinkCard]


_SLUG_SEPARATORS = re.compile(r"[ _]")
_NOT_SLUG = re.compile(r"[^a-z0-9-]")


def section_slug(title: str) -> str:
    """The path segment for a `Section` value. `AI Agents` becomes `ai-agents`."""
    return _NOT_SLUG.sub("", _SLUG_SEPARATORS.sub("-", title.strip().lower()))


#: The tab for the cards with no section, on a page where other cards have one.
MISC_TITLE = "Misc"
MISC_SLUG = section_slug(MISC_TITLE)


def tab_slug(section: str) -> str:
    """The slug of the tab that a card with this `Section` value shows in."""
    return section_slug(section) or MISC_SLUG


def sections(model: PageModel) -> list[Section]:
    """The page's tabs, in the order of their first card.

    Values with the same slug are one tab, titled by the first value. A card with no
    section, or one whose slug is empty, goes in the Misc tab. A page where no card
    has a section is one untitled section.
    """
    if not any(section_slug(card.section) for card in model.cards):
        return [Section("", "", list(model.cards))]

    tabs: dict[str, Section] = {}
    for card in model.cards:
        slug = tab_slug(card.section)
        if slug not in tabs:
            title = card.section.strip() if section_slug(card.section) else MISC_TITLE
            tabs[slug] = Section(title, slug, [])
        tabs[slug].cards.append(card)
    return list(tabs.values())


def find_section(tabs: list[Section], slug: str) -> Section | None:
    """The tab whose path segment is `slug`, or None. An empty slug matches nothing."""
    return next((tab for tab in tabs if slug and tab.slug == slug), None)


def escape_html(value: str) -> str:
    """The five replacements the TypeScript build makes, in the same order.

    Not `html.escape`, which emits `&#x27;` for an apostrophe where the
    TypeScript `escapeHtml` emits `&#39;`.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def safe_url(value: str) -> str:
    """Allow only http(s) and mailto: hrefs into the document.

    Anything else — javascript:, data:, a malformed string from Notion —
    collapses to "#".
    """
    if is_mailto_url(value):
        return normalize_mailto(value)
    parsed = parse_url(value)
    if parsed is None or parsed.scheme not in ("http", "https"):
        return "#"
    return parsed.href()


# One mask rule per icon file. The rules are generated into the <style> block,
# because the policy allows that block by hash and no style attribute at all.
ICON_MASKS = "\n".join(
    f".card__mark--{name} {{ --mark: url('/links/assets/link-icons/{name}."
    f"{'svg' if name in SVG_ICONS else 'png'}'); }}"
    for name in ICON_NAMES
    if name not in ORDINALS
)

_STYLES_HEAD = """
@font-face {
  font-family: 'PP Neue Montreal';
  src: url('/links/assets/fonts/PPNeueMontreal-Variable.woff2') format('woff2-variations');
  font-weight: 300 500;
  font-display: swap;
}

:root {
  --bg: #FFFFFF;
  --text: #0D0D0D;
  --text-secondary: #4D4D4D;
  --text-faint: #6B6B6B;
  --hairline: #E3E3E3;
  --focus: #6C35F5;
  --tabs-bg: color-mix(in srgb, var(--text) 5%, transparent);
  --tab-selected-bg: var(--bg);
  --tab-selected-ring: #00000012;

  /* The theme toggle shows the moon in light mode and the sun in dark mode. */
  --toggle-moon: block;
  --toggle-sun: none;

  --radius-control: 4px;
  --radius-card: 8px;
  --radius-button: 2px;
  --grid-margin: 32px;
  --ease: cubic-bezier(0.9, 0.1, 0.1, 0.9);

  --font-default: 'PP Neue Montreal', ui-sans-serif, system-ui, sans-serif;

  color-scheme: light;
}
"""

# The dark tokens apply when the system is dark and the visitor did not choose light,
# or when the visitor chose dark. THEME_SCRIPT sets data-theme from the saved choice.
_DARK_TOKENS = """
  --bg: #0D0D0D;
  --text: #FFFFFF;
  --text-secondary: #C7C7C7;
  --text-faint: #B3B3B3;
  --hairline: #272727;
  --focus: #B3B1FA;
  --tabs-bg: color-mix(in srgb, var(--text) 8%, transparent);
  --tab-selected-bg: color-mix(in srgb, var(--text) 12%, var(--bg));
  --tab-selected-ring: #ffffff0d;
  --toggle-moon: none;
  --toggle-sun: block;
  color-scheme: dark;
"""

_STYLES_DARK = f"""
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{{_DARK_TOKENS}  }}
}}

:root[data-theme="dark"] {{{_DARK_TOKENS}}}
"""

_STYLES_BASE = """
*, *::before, *::after { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  position: relative;
  margin: 0;
  min-height: 100svh;
  display: flex;
  justify-content: center;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-default);
  font-weight: 400;
  font-size: 16px;
  line-height: 1.5;
  letter-spacing: 0.01em;
  -webkit-font-smoothing: antialiased;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.page {
  width: 100%;
  max-width: calc(480px + 2 * var(--grid-margin));
  padding: 80px var(--grid-margin) 24px;
  display: flex;
  flex-direction: column;
}

.header { display: flex; justify-content: center; }

.logo { display: block; }
.logo:focus-visible { outline: 2px solid var(--focus); outline-offset: 4px; }

/*
 * A mask painted with the text color, so the logo follows the color scheme.
 * The mask is on a child, because a mask on the link would also clip its focus ring.
 */
.logo__mark {
  display: block;
  width: 112px;
  height: 24px;
  background-color: var(--text);
  -webkit-mask: url('/links/assets/render-logo.svg') center / contain no-repeat;
  mask: url('/links/assets/render-logo.svg') center / contain no-repeat;
}

/*
 * The theme toggle, in the top right corner of the page and level with the logo.
 * It is hidden until PAGE_SCRIPT runs, because it does nothing without the script.
 */
.theme-toggle {
  position: absolute;
  top: 72px;
  right: var(--grid-margin);
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-control);
  background: none;
  color: var(--text-faint);
  cursor: pointer;
}
.theme-toggle[hidden] { display: none; }
.theme-toggle:hover { color: var(--text); }
.theme-toggle:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }

.theme-toggle__icon {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.theme-toggle__moon { display: var(--toggle-moon); }
.theme-toggle__sun { display: var(--toggle-sun); }

.main {
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding-top: 56px;
}

.intro {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
}

.intro__title {
  margin: 0;
  font-size: 32px;
  font-weight: 500;
  line-height: 1.125;
  letter-spacing: -0.02em;
  text-wrap: balance;
}

/*
 * The profile's tagline, under the name in the intro block. The class follows the
 * redesign's block__element names. _render_intro leaves it out on the default page.
 */
.intro__text {
  margin: 0;
  max-width: 36ch;
  color: var(--text-secondary);
  text-wrap: pretty;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tabs {
  display: flex;
  gap: 2px;
  padding: 2px;
  border-radius: calc(var(--radius-control) + 2px);
  background: var(--tabs-bg);
}

.tab {
  flex: 1 1 0%;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 12px;
  border-radius: var(--radius-control);
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  letter-spacing: 0;
  text-align: center;
  color: var(--text-faint);
  text-decoration: none;
}
.tab:hover { color: var(--text); }
.tab[aria-current="page"] {
  background: var(--tab-selected-bg);
  color: var(--text);
  box-shadow: 0 0 0 1px var(--tab-selected-ring);
}
.tab:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

.links {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
/* The display rule above would show the lists of the other tabs. */
.links[hidden] { display: none; }

.card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  padding: 7px 16px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-card);
  background: var(--bg);
  color: var(--text);
  text-decoration: none;
}
.card:hover { border-color: var(--text-faint); }
.card:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

/*
 * The icon files are dark artwork on transparency, so an <img> would disappear
 * against the dark background. Each one is a mask instead, painted with the
 * faint text color.
 */
.card__mark {
  flex: none;
  width: 20px;
  height: 20px;
  background-color: var(--text-faint);
  -webkit-mask: var(--mark) center / contain no-repeat;
  mask: var(--mark) center / contain no-repeat;
}
"""

_STYLES_TAIL = """

/* The 2px side margins make the box as wide as the 20px icon column. */
.card__step {
  flex: none;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  margin: 0 2px;
  border: 1.25px solid;
  border-radius: var(--radius-button);
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
}

.card__body {
  flex: 1 1 0%;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.card__title {
  font-size: 16px;
  line-height: 24px;
  font-weight: 500;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

.card__hint {
  font-size: 14px;
  line-height: 16px;
  color: var(--text-faint);
}

.card__go {
  flex: none;
  width: 16px;
  height: 16px;
  background-color: var(--text-faint);
  -webkit-mask: url('/links/assets/go.svg') center / contain no-repeat;
  mask: url('/links/assets/go.svg') center / contain no-repeat;
  transition: translate 200ms var(--ease);
}
.card:hover .card__go {
  background-color: var(--text);
  translate: 2px;
}

.socials {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
}

.social {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-control);
  color: var(--text-faint);
}
.social:hover { color: var(--text); }
.social:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }

/*
 * The icon files are black glyphs used as CSS masks. They take the text
 * color (currentColor), so they follow both color schemes.
 */
.social__icon {
  display: block;
  width: 18px;
  height: 18px;
  background-color: currentColor;
  -webkit-mask: var(--icon) center / contain no-repeat;
  mask: var(--icon) center / contain no-repeat;
}

.social__icon--youtube { --icon: url('/links/assets/icons/youtube.svg'); }
.social__icon--linkedin { --icon: url('/links/assets/icons/linkedin.svg'); }
.social__icon--x { --icon: url('/links/assets/icons/x.svg'); }
.social__icon--github { --icon: url('/links/assets/icons/github.svg'); }
.social__icon--discord { --icon: url('/links/assets/icons/discord.svg'); }

.footer {
  margin-top: auto;
  padding-top: 48px;
  font-size: 14px;
  line-height: 1.429;
  color: var(--text-faint);
  text-align: center;
}

@media (max-width: 1023.98px) {
  :root { --grid-margin: 24px; }
  .intro__title { font-size: 28px; }
}

@media (max-width: 767.98px) {
  :root { --grid-margin: 16px; }
  .intro__title { font-size: 24px; }
  .page { padding-top: 32px; }
  .theme-toggle { top: 22px; width: 44px; height: 44px; }
  .main { gap: 24px; padding-top: 40px; }
  .tab { min-height: 40px; }
  .social { width: 44px; height: 44px; }
}

@media (prefers-reduced-motion: reduce) {
  .card__go { transition: none; }
}
"""

STYLES = _STYLES_HEAD + _STYLES_DARK + _STYLES_BASE + ICON_MASKS + _STYLES_TAIL

# Applies the saved theme in the head, so the page does not paint in the wrong theme
# first. Storage can be blocked, for example in a private window.
THEME_SCRIPT = """
try {
  var theme = localStorage.getItem('theme');
  if (theme === 'light' || theme === 'dark') {
    document.documentElement.dataset.theme = theme;
  }
} catch (error) {}
"""

# An email card links to mailto:, which opens the mail app on a phone. A desktop
# often has no mail app, so a mouse or trackpad swaps in Gmail's compose page, which
# opens in a new tab. The script then adds the same hidden text as a web card.
PAGE_SCRIPT = """
if (matchMedia('(hover: hover) and (pointer: fine)').matches) {
  document.querySelectorAll('a[data-gmail]').forEach(function (a) {
    a.href = a.dataset.gmail;
    a.target = '_blank';
    a.rel = 'noreferrer';
    var note = document.createElement('span');
    note.className = 'visually-hidden';
    note.textContent = '(opens in a new tab)';
    a.append(note);
  });
}

// A tab click shows its links in place, so the header does not load again.
// Each tab is also a full link, for a new tab, a copied URL, or no script.
var tabs = document.querySelectorAll('.tab[data-section]');

function showSection(slug) {
  tabs.forEach(function (tab) {
    if (tab.dataset.section === slug) {
      tab.setAttribute('aria-current', 'page');
    } else {
      tab.removeAttribute('aria-current');
    }
  });
  document.querySelectorAll('.links[data-section]').forEach(function (list) {
    list.hidden = list.dataset.section !== slug;
  });
}

tabs.forEach(function (tab) {
  tab.addEventListener('click', function (event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    if (tab.getAttribute('aria-current') === 'page') {
      return;
    }
    showSection(tab.dataset.section);
    history.pushState({ section: tab.dataset.section }, '', tab.href);
  });
});

if (tabs.length) {
  var opened = document.querySelector('.tab[aria-current="page"]').dataset.section;
  history.replaceState({ section: opened }, '');
  addEventListener('popstate', function (event) {
    showSection(event.state && event.state.section ? event.state.section : opened);
  });
}

// The theme toggle saves the choice, and THEME_SCRIPT applies it on the next load.
// With no saved choice, the page follows the system theme.
var toggle = document.querySelector('.theme-toggle');
var darkScheme = matchMedia('(prefers-color-scheme: dark)');

function isDark() {
  var theme = document.documentElement.dataset.theme;
  return theme ? theme === 'dark' : darkScheme.matches;
}

function showTheme() {
  toggle.setAttribute('aria-pressed', String(isDark()));
}

toggle.addEventListener('click', function () {
  var theme = isDark() ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem('theme', theme);
  } catch (error) {}
  showTheme();
});
darkScheme.addEventListener('change', showTheme);
showTheme();
toggle.hidden = false;
"""


def _sha256_source(content: str) -> str:
    """CSP source expression for an inline block, so the policy allows it by hash."""
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


CSP = "; ".join(
    [
        "default-src 'none'",
        # 'self' covers the logo, the icons, and the other assets the site ships, so
        # they also load over plain http on localhost.
        "img-src 'self'",
        f"style-src {_sha256_source(STYLES)}",
        f"script-src {_sha256_source(THEME_SCRIPT)} {_sha256_source(PAGE_SCRIPT)}",
        "font-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
    ]
)

NEW_TAB_TEXT = '<span class="visually-hidden">(opens in a new tab)</span>'
MAILTO_HINT = '<span class="card__hint">Opens your email app</span>'

# A moon in light mode and a sun in dark mode. The --toggle-moon and --toggle-sun
# tokens show one of them.
THEME_TOGGLE = """<button class="theme-toggle" type="button" aria-label="Dark mode" aria-pressed="false" hidden>
        <svg class="theme-toggle__icon theme-toggle__moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.25 14.25A8.25 8.25 0 0 1 9.75 3.75a8.25 8.25 0 1 0 10.5 10.5z"/></svg>
        <svg class="theme-toggle__icon theme-toggle__sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.75v1.5M12 19.75v1.5M2.75 12h1.5M19.75 12h1.5M5.46 5.46l1.06 1.06M17.48 17.48l1.06 1.06M5.46 18.54l1.06-1.06M17.48 6.52l1.06-1.06"/></svg>
      </button>"""


def _render_card(card: LinkCard) -> str:
    href = escape_html(safe_url(card.url))
    title = f'<span class="card__title">{escape_html(card.title)}</span>'
    if is_mailto_url(card.url):
        # PAGE_SCRIPT swaps this in for the mailto: href on a desktop.
        attributes = f' data-gmail="{escape_html(gmail_compose_url(card.url))}"'
        body = title + MAILTO_HINT
        new_tab = ""
    else:
        attributes = ' target="_blank" rel="noreferrer"'
        body = title
        new_tab = f"\n            {NEW_TAB_TEXT}"

    number = ORDINALS.get(card.icon)
    if number is None:
        mark = (
            f'<span class="card__mark card__mark--{escape_html(card.icon)}" '
            'aria-hidden="true"></span>'
        )
    else:
        mark = f'<span class="card__step" aria-hidden="true">{number}</span>'
        body = f'<span class="visually-hidden">Step {number}: </span>' + body

    return f"""          <a class="card" href="{href}"{attributes}>
            {mark}
            <span class="card__body">{body}</span>
            <span class="card__go" aria-hidden="true"></span>{new_tab}
          </a>"""


#: Where the logo links.
LOGO_HREF = "https://render.com/"

#: Link previews need an absolute URL, so this is the render.com path of
#: assets/preview.png.
PREVIEW_IMAGE_URL = "https://render.com/links/assets/preview.png"

# The icon row under the links. It is the same on every page and does not come
# from Notion. Each label needs a matching file under grouplink/assets/icons and a
# .social__icon--<label> rule in STYLES.
SOCIALS: list[SocialLink] = [
    SocialLink("YouTube", "https://www.youtube.com/@render-inc"),
    SocialLink("LinkedIn", "https://www.linkedin.com/company/renderco"),
    SocialLink("X", "https://x.com/render"),
    SocialLink("GitHub", "https://github.com/render-oss"),
    SocialLink("Discord", "https://render.com/discord"),
]


def _render_social(social: SocialLink) -> str:
    href = escape_html(safe_url(social.url))
    icon = escape_html(social.label.strip().lower())
    label = escape_html(social.label)
    return (
        f'        <a class="social" href="{href}" target="_blank" rel="noreferrer" '
        f'aria-label="{label}"><span class="social__icon social__icon--{icon}"></span></a>'
    )


# A run of ASCII whitespace that holds at least one line break.
_LINE_BREAK_RUN = re.compile(r"[ \t\r\n\f\v]*\n[ \t\r\n\f\v]*")


def _one_line(tagline: str) -> str:
    """Collapse every run of whitespace around a line break into a single space."""
    return _LINE_BREAK_RUN.sub(" ", tagline).strip()


def _render_intro(name: str, tagline: str, is_default: bool) -> str:
    """The profile name, then the tagline. The default page and an empty tagline
    show no tagline paragraph.
    """
    title = f'        <h1 class="intro__title">{escape_html(name)}</h1>'
    text = (
        f'\n        <p class="intro__text">{escape_html(tagline)}</p>'
        if tagline and not is_default
        else ""
    )
    return f'      <div class="intro">\n{title}{text}\n      </div>'


def _render_tab(tab: Section, is_current: bool, is_first: bool, profile_slug: str) -> str:
    # The first tab's URL is the profile path, so each tab has one URL.
    path = f"/links/{profile_slug}" if is_first else f"/links/{profile_slug}/{tab.slug}"
    href = escape_html(path)
    current = ' aria-current="page"' if is_current else ""
    section = escape_html(tab.slug)
    return (
        f'          <a class="tab" href="{href}" data-section="{section}"{current}>'
        f"{escape_html(tab.title)}</a>"
    )


def _render_tabs(tabs: list[Section], current: Section, profile_slug: str) -> str:
    """The tab row, or "" when the page has fewer than two sections."""
    if len(tabs) < 2:
        return ""
    links = "\n".join(
        _render_tab(tab, tab is current, tab is tabs[0], profile_slug) for tab in tabs
    )
    return f"""        <nav class="tabs" aria-label="Sections">
{links}
        </nav>
"""


def _render_list(cards: list[LinkCard], attributes: str) -> str:
    items = "\n".join(_render_card(card) for card in cards)
    return f'        <div class="links"{attributes}>\n{items}\n        </div>'


def _render_lists(tabs: list[Section], current: Section) -> str:
    """One list of cards per tab. Only the current tab's list shows.

    The page has every tab's cards, so the script can change tabs with no request.
    """
    if len(tabs) < 2:
        return _render_list(current.cards, "")
    return "\n".join(
        _render_list(
            tab.cards,
            f' data-section="{escape_html(tab.slug)}"' + ("" if tab is current else " hidden"),
        )
        for tab in tabs
    )


def render_page(
    model: PageModel,
    year: int | None = None,
    *,
    profile_slug: str,
    section: str | None = None,
    is_default: bool = False,
) -> str:
    """`year` is the footer's copyright year, read from the clock when it is None.
    Taking it as an argument keeps the golden test stable across a new year.

    `section` is the slug of the tab to show, and None means the first one. The tabs link
    to `/links/<profile_slug>/<section>`. Raises ValueError for a section the page
    does not have.

    `is_default` is true for the site's default profile. Its page shows no tagline
    paragraph. The meta tags hold the tagline on every page.
    """
    footer_year = date.today().year if year is None else year
    tagline_text = _one_line(model.tagline)
    tabs = sections(model)
    current = tabs[0] if section is None else find_section(tabs, section)
    if current is None:
        raise ValueError(f'the page has no section "{section}"')
    intro = _render_intro(model.name, tagline_text, is_default)
    tabs_block = _render_tabs(tabs, current, profile_slug)
    lists = _render_lists(tabs, current)
    socials = "\n".join(_render_social(social) for social in SOCIALS)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>Render Links</title>
<meta name="description" content="{escape_html(tagline_text)}">
<meta property="og:title" content="{escape_html(model.name)} — links">
<meta property="og:description" content="{escape_html(tagline_text)}">
<meta property="og:type" content="website">
<meta property="og:image" content="{PREVIEW_IMAGE_URL}">
<meta property="og:image:width" content="1600">
<meta property="og:image:height" content="900">
<meta property="og:image:alt" content="Render: Your fastest path to production">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/links/assets/render-logomark-black.svg" media="(prefers-color-scheme: light)">
<link rel="icon" href="/links/assets/render-logomark-white.svg" media="(prefers-color-scheme: dark)">
<style>{STYLES}</style>
<script>{THEME_SCRIPT}</script>
</head>
<body>
  <div class="page">
    <header class="header">
      <a class="logo" href="{LOGO_HREF}" aria-label="Render home"><span class="logo__mark"></span></a>
      {THEME_TOGGLE}
    </header>
    <main class="main">
{intro}
      <div class="sections">
{tabs_block}{lists}
      </div>
      <nav class="socials" aria-label="Render on social media">
{socials}
      </nav>
    </main>
    <footer class="footer">&copy; {footer_year} Render Inc.</footer>
  </div>
<script>{PAGE_SCRIPT}</script>
</body>
</html>
"""
