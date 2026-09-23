"""Which pages the article-only signals apply to.

Authorship, attribution and Article markup ask who wrote a piece and when. A
home page, a product, a tool or an index was not written by anyone in that
sense, and scoring it at zero for lacking a byline reports a consequence as a
failure: the practitioner eval named a home page "the first example page for
authorship, where no byline belongs".

A page is excluded only on evidence the site itself gives: where it sits, what
it lists beneath itself, what it declares itself to be. Nothing here guesses
from the prose, because a guess that drops a real article loses a real finding,
and a page with no evidence either way is presumed an article, as every page
was before - unless the site itself has answered the question. A site that marks its
articles, in JSON-LD or `og:type`, has said what the pages it left unmarked are not, and
that beats a presumption made from one page. Only an audit can ask it: `geo score` reads
a page with no other page of the same site beside it. Sampled on 79 pages from eight
real sites, the page rules kept all 31 articles and excluded 27 of the 48 other pages.

A category, tag or author archive is an index whose pages do not sit beneath it:
seomator.com's `/blog/category/backlinks` lists posts at `/blog/<slug>`, so the
links-beneath rule missed seven of them, and two findings named nothing but those
archives and an about page. Where such a page sits is the evidence: the path a CMS
gives its archives.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from geo_audit import data
from geo_audit.lib.extract import Document
from geo_audit.scoring.model import NOT_APPLICABLE

# The reason an article-only signal gives on a page that is not an article.
ARTICLES_ONLY = f"{NOT_APPLICABLE}: articles only"

# `/`, or a bare locale such as `/en-US/` or `/de`.
_HOME = re.compile(r"/?(?:[a-z]{2}(?:[-_][a-z]{2,4})?/?)?", re.IGNORECASE)
# `.../category/<name>`, `.../tag/<name>`, `.../author/<name>` and their plurals,
# optionally paged: where CMSs put the lists of posts filed under one term. German
# `kategorie` too, which seomator.com's `/de/blog/kategorie/<name>` uses. A CMS that
# cannot nest a collection qualifies the word instead - userguiding.com files the
# same lists under `/blog-category/<name>` - so one hyphenated prefix is allowed.
_ARCHIVE = re.compile(
    r".*/(?:[^/]+-)?(category|categories|kategorie|kategorien|tag|tags|author|authors)/[^/]+(?:/page/\d+)?/?",
    re.IGNORECASE,
)
_ARCHIVE_OF = {"categor": "a category", "kategor": "a category", "tag": "a tag", "author": "an author"}


def declared_types(doc: Document) -> set[str]:
    """What a page says it is: its top-level JSON-LD nodes and `@graph` members.

    Nested values are what a page talks about, not what it is: a review names
    the app it reviews without being one.
    """
    found: set[str] = set()
    for entry in doc.jsonld:
        for node in entry if isinstance(entry, list) else [entry]:
            if not isinstance(node, dict):
                continue
            members = node.get("@graph")
            for member in [node, *(members if isinstance(members, list) else [])]:
                kind = member.get("@type") if isinstance(member, dict) else None
                if isinstance(kind, str):
                    found.add(kind)
                elif isinstance(kind, list):
                    found.update(str(k) for k in kind)
    return found


# Two pages, not one: a stray Article blob on a landing page is not a convention.
_MARKED_MIN_PAGES = 2


def marks_an_article(doc: Document) -> bool:
    """Whether the page says, in either place a site says it, that it is an article."""
    if declared_types(doc) & set(data.load("schema_requirements")["article_types"]):
        return True
    return (doc.meta.get("og:type") or "").strip().lower() == "article"


def marks_its_articles(docs) -> bool:
    """Whether the site says which of its pages are articles.

    A site that marks its articles has answered the question for every page it
    left unmarked, and that answer beats a presumption made from the page
    alone. Only an audit can ask it: `geo score` reads one page and has no
    other page of the site to compare it with.
    """
    marked = 0
    for doc in docs:
        marked += marks_an_article(doc)
        if marked >= _MARKED_MIN_PAGES:
            return True
    return False


def not_an_article(doc: Document, site_marks_articles: bool = False) -> str | None:
    """Why the page is plainly not an article, or None to treat it as one."""
    path = urlsplit(doc.url).path
    if _HOME.fullmatch(path):
        return "the site's home page"

    # A page that declares itself an article is one, even a guide whose
    # chapters sit beneath it.
    declared = declared_types(doc)
    requirements = data.load("schema_requirements")
    if declared & set(requirements["article_types"]):
        return None

    # A blog index or a directory links down into its own path; an article
    # links across to its neighbours.
    beneath = path.rstrip("/") + "/"
    children = {
        urlsplit(link).path.rstrip("/")
        for link in doc.internal_links
        if urlsplit(link).path.startswith(beneath) and urlsplit(link).path.rstrip("/") != path.rstrip("/")
    }
    if len(children) >= data.thresholds("articles")["index_min_children"]:
        return f"an index of {len(children)} pages beneath it"
    archive = _ARCHIVE.fullmatch(path)
    if archive:
        kind = next(name for stem, name in _ARCHIVE_OF.items() if archive.group(1).lower().startswith(stem))
        return f"{kind} archive"

    for kind in requirements["not_article_types"]:
        if kind in declared:
            return f"declared a {kind}"
    og_type = (doc.meta.get("og:type") or "").strip().lower()
    if og_type.startswith("product") or og_type == "profile":
        return f"declared og:type {og_type}"

    # Last, because every rule above reads this page; this one reads the site.
    if site_marks_articles and not marks_an_article(doc):
        return "the site marks its articles and not this page"
    return None


def exempt(doc: Document, site_marks_articles: bool = False) -> tuple[None, dict] | None:
    """What an article-only signal returns on a page that is not an article."""
    reason = not_an_article(doc, site_marks_articles)
    if reason is None:
        return None
    return None, {"reason": ARTICLES_ONLY, "not_an_article": reason}
