"""The normalizer: HTML in, a content-block sequence out.

This module defines what the scorer sees and therefore what the evidence hash
covers. Changing it changes hash identity for every page in existence, which is
why `normalizer_version` exists and why it is stamped into the hash input.

The design constraint: re-fetching a page whose only changes are a CSP nonce, a
"generated at" timestamp and a rotated ad slot must produce the same hash. So
boilerplate is removed structurally (landmarks and well-known chrome patterns),
not by diffing two fetches.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

BLOCK_TAGS = (
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "li", "blockquote", "pre", "dt", "dd", "td", "th", "figcaption",
)

# Removed everywhere: never content, and several are injection surfaces.
DROP_TAGS = (
    "script", "style", "template", "svg", "canvas", "iframe", "object",
    "embed", "form", "button", "select", "textarea", "video", "audio",
    "map", "dialog",
)

# Removed inside the content root: chrome that repeats on every page.
CHROME_TAGS = ("nav", "aside")

# Removed when the page has no semantic content root and we fall back to <body>.
FALLBACK_CHROME_TAGS = ("nav", "aside", "header", "footer")

CHROME_ROLES = frozenset(
    {"navigation", "banner", "contentinfo", "complementary", "search", "menubar"}
)

CHROME_PATTERN = re.compile(
    r"(?:^|[-_ ])(?:ad|ads|advert|advertisement|promo|sponsor|banner|cookie|"
    r"consent|newsletter|subscribe|signup|social|share|sharing|breadcrumb|"
    r"pagination|pager|sidebar|widget|related|recirc|comments?|disqus|"
    r"skip-link|screen-reader|sr-only|visually-hidden)(?:[-_ ]|$)",
    re.IGNORECASE,
)

# Framework mount points. A page whose mount point is empty in the raw response
# is client-rendered whether or not it bothers to say so in a <noscript>.
FRAMEWORK_ROOT_ID = re.compile(r"^(?:app|root|__next|__nuxt|__layout|svelte)$", re.IGNORECASE)

JS_REQUIRED_PATTERN = re.compile(
    r"(?:enable|turn on|requires?|needs?)\s+javascript|javascript\s+is\s+"
    r"(?:required|disabled)|you\s+need\s+to\s+enable\s+js",
    re.IGNORECASE,
)

_WS = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return _WS.sub(" ", value).strip()


@dataclass(frozen=True)
class Block:
    kind: str
    text: str
    section: int

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Document:
    url: str
    lang: str | None = None
    title: str | None = None
    meta: dict[str, str] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    headings: list[tuple[int, str]] = field(default_factory=list)
    jsonld: list[dict] = field(default_factory=list)
    jsonld_errors: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)
    content_root: str = "body"
    body_chars: int = 0
    lists: int = 0
    tables: int = 0
    images: int = 0
    images_with_alt: int = 0
    js_required_notice: bool = False
    framework_root_chars: int | None = None

    @property
    def content_chars(self) -> int:
        return sum(len(b.text) for b in self.blocks)

    @property
    def prose_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.kind in ("p", "li", "blockquote", "dd")]


def _is_chrome(tag: Tag) -> bool:
    role = tag.get("role")
    if isinstance(role, str) and role.strip().lower() in CHROME_ROLES:
        return True
    tokens = []
    css_class = tag.get("class")
    if css_class:
        tokens.extend(css_class if isinstance(css_class, list) else [css_class])
    tag_id = tag.get("id")
    if isinstance(tag_id, str):
        tokens.append(tag_id)
    return any(CHROME_PATTERN.search(str(token)) for token in tokens)


def _pick_root(soup: BeautifulSoup) -> tuple[Tag, str]:
    """Choose the element that holds the page's own content.

    `<main>` first, then a *single* `<article>`, then `role="main"`, then the
    body.

    The single-article rule is the important one. On an article page there is
    one `<article>` and it is exactly the content. On a homepage or a listing
    there are a dozen, each a teaser, and taking the first one throws the page
    away: eff.org's homepage reduced to fifty characters of one card, and was
    then scored as though that were the whole site.

    Being the only `<article>` is not enough on its own either. userguiding.com
    wraps its promo banner in one, and every page on the site - the homepage,
    the blog, 950 posts - was read as the banner alone.
    """
    node = soup.find("main")
    if isinstance(node, Tag):
        return node, "main"

    articles = [n for n in soup.find_all("article") if isinstance(n, Tag)]
    if len(articles) == 1 and _holds_the_page(articles[0], soup):
        return articles[0], "article"

    node = soup.find(attrs={"role": "main"})
    if isinstance(node, Tag):
        return node, "role=main"
    body = soup.body
    if isinstance(body, Tag):
        return body, "body"
    return soup, "document"


MIN_ROOT_SHARE = 0.10


def _holds_the_page(candidate: Tag, soup: BeautifulSoup) -> bool:
    """Does this element carry the page's text, or only sit in it?

    Measured after the chrome inside the candidate is gone, because that is
    what the scorer would see. Real articles carry almost all of it -
    smashingmagazine posts measure 0.89 and 0.90 - and a banner dressed as an
    `<article>` carries none: userguiding.com's is 0.00 of an 11,000-character
    page. Nothing observed lands near the line between them.
    """
    body = soup.body if isinstance(soup.body, Tag) else soup
    page_chars = len(normalize_text(body.get_text(" ")))
    if not page_chars:
        return True
    trial = copy.copy(candidate)
    _strip(trial, CHROME_TAGS)
    return len(normalize_text(trial.get_text(" "))) / page_chars >= MIN_ROOT_SHARE


def _collect_jsonld(soup: BeautifulSoup) -> tuple[list[dict], list[str]]:
    blocks: list[dict] = []
    errors: list[str] = []
    for node in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = node.string or node.get_text() or ""
        if not raw.strip():
            errors.append("empty ld+json block")
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON at line {exc.lineno}: {exc.msg}")
            continue
        graph = parsed.get("@graph") if isinstance(parsed, dict) else None
        items = graph if isinstance(graph, list) else parsed
        for item in items if isinstance(items, list) else [items]:
            if isinstance(item, dict):
                blocks.append(item)
            else:
                errors.append("ld+json entry is not an object")
    return blocks, errors


def _collect_meta(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}
    for node in soup.find_all("meta"):
        key = node.get("name") or node.get("property") or node.get("itemprop")
        value = node.get("content")
        if isinstance(key, str) and isinstance(value, str):
            meta.setdefault(key.strip().lower(), normalize_text(value))
    canonical = soup.find("link", attrs={"rel": re.compile(r"^canonical$", re.I)})
    if isinstance(canonical, Tag) and isinstance(canonical.get("href"), str):
        meta["canonical"] = canonical["href"].strip()
    return meta


def _strip(root: Tag, chrome_tags: tuple[str, ...]) -> None:
    for node in root.find_all(chrome_tags):
        node.decompose()
    for node in list(root.find_all(True)):
        if node.parent is None:
            continue
        if _is_chrome(node):
            node.decompose()


def extract(html: str, url: str) -> Document:
    soup = BeautifulSoup(html, "html.parser")
    doc = Document(url=url)

    html_tag = soup.find("html")
    if isinstance(html_tag, Tag) and isinstance(html_tag.get("lang"), str):
        doc.lang = html_tag["lang"].strip() or None

    title_tag = soup.find("title")
    if isinstance(title_tag, Tag):
        doc.title = normalize_text(title_tag.get_text()) or None

    doc.meta = _collect_meta(soup)
    doc.jsonld, doc.jsonld_errors = _collect_jsonld(soup)

    noscript_text = " ".join(normalize_text(n.get_text()) for n in soup.find_all("noscript"))

    # Measured before anything is stripped: decomposing scripts would change what
    # a mount point appears to contain.
    mounts = [n for n in soup.find_all(id=FRAMEWORK_ROOT_ID) if isinstance(n, Tag)]
    if mounts:
        doc.framework_root_chars = min(
            len(normalize_text(mount.get_text(" "))) for mount in mounts
        )

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for node in soup.find_all(DROP_TAGS + ("noscript",)):
        node.decompose()

    body = soup.body if isinstance(soup.body, Tag) else soup
    doc.body_chars = len(normalize_text(body.get_text(" ")))
    doc.js_required_notice = bool(
        JS_REQUIRED_PATTERN.search(noscript_text)
        or JS_REQUIRED_PATTERN.search(normalize_text(body.get_text(" ")))
    )

    root, root_name = _pick_root(soup)
    doc.content_root = root_name
    _strip(root, FALLBACK_CHROME_TAGS if root_name in ("body", "document") else CHROME_TAGS)

    doc.lists = len(root.find_all(("ul", "ol")))
    doc.tables = len(root.find_all("table"))
    for img in root.find_all("img"):
        doc.images += 1
        alt = img.get("alt")
        if isinstance(alt, str) and alt.strip():
            doc.images_with_alt += 1

    page_host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for anchor in root.find_all("a"):
        href = anchor.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        target = urljoin(url, href.strip())
        scheme = urlsplit(target).scheme.lower()
        if scheme not in ("http", "https"):
            continue
        host = (urlsplit(target).hostname or "").lower().removeprefix("www.")
        if host and host != page_host:
            doc.external_links.append(target)
        else:
            doc.internal_links.append(target)

    if doc.title:
        doc.blocks.append(Block(kind="title", text=doc.title, section=-1))

    section = -1
    for node in root.find_all(BLOCK_TAGS):
        if any(isinstance(p, Tag) and p.name in BLOCK_TAGS for p in node.parents):
            continue
        text = normalize_text(node.get_text(" "))
        if not text:
            continue
        kind = node.name
        if kind in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(kind[1])
            doc.headings.append((level, text))
            if level <= 2:
                section += 1
        doc.blocks.append(Block(kind=kind, text=text, section=section))

    return doc


def excerpt(text: str, limit: int = 280) -> str:
    """A length-capped, delimiter-escaped quote.

    The escaping matters as much as the cap: an excerpt is shown inside a
    prompt, and a page that contains a fenced code block or an XML-ish tag
    should not be able to close the surrounding context.
    """
    clean = normalize_text(text)
    clean = clean.replace("`", "'").replace("<", "‹").replace(">", "›")
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"
