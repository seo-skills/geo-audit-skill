"""Expertise is judged on the article's author, not on the first Person found.

seomator.com's posts name their author in `BlogPosting.author`, with a profile
URL, a job title and a description. Every page also carries the company's
Organization graph, whose `parentOrganization.founder` is a Person with a name
and nothing else - and it comes first. Expertise took the first Person on the
page, so all 43 posts read as missing credentials and an author profile, and
the report's first fix told the site to add what it already had.
"""

from __future__ import annotations

import json

from geo_audit.lib.extract import extract
from geo_audit.scoring import content

URL = "https://example.com/blog/a-post"
PROSE = "<p>" + "A sentence of real prose about the thing this post explains. " * 30 + "</p>"
FOUNDER_GRAPH = {
    "@context": "https://schema.org",
    "@graph": [{
        "@type": "Organization", "name": "Acme",
        "parentOrganization": {"@type": "Organization", "name": "Acme Holdings",
                               "founder": {"@type": "Person", "@id": "https://example.com/#founder", "name": "Founder"}},
    }],
}
AUTHOR = {"@type": "Person", "name": "Isabella Edwards", "url": "https://example.com/team/isabella",
          "jobTitle": "Technical SEO Content Manager", "description": "Leads technical SEO content."}


def _doc(*blocks, meta: str = ""):
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(block)}</script>' for block in blocks)
    html = f"<html><head><title>t</title>{meta}{scripts}</head><body><main><h1>Post</h1>{PROSE}</main></body></html>"
    return extract(html, URL)


def test_the_article_author_is_read_past_a_founder_in_the_site_graph():
    points, detail = content.expertise(_doc(FOUNDER_GRAPH, {"@type": "BlogPosting", "headline": "h", "author": [AUTHOR]}))
    assert points == 25
    assert {"credentials", "author_profile"} <= set(detail["present"])
    assert detail["byline"] == "Isabella Edwards"


def test_a_founder_is_not_the_author_of_a_page_that_names_none():
    points, detail = content.expertise(_doc(FOUNDER_GRAPH, {"@type": "BlogPosting", "headline": "h"}))
    assert {"byline", "person_schema", "credentials", "author_profile"} <= set(detail["missing"])
    assert points == 3, "the Organization still counts"


def test_an_author_given_by_reference_is_resolved_in_the_graph():
    """The common plugin shape: the article points at a Person node by @id."""
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "Article", "headline": "h", "author": {"@id": "https://example.com/#/person/1"}},
        {"@type": "Person", "@id": "https://example.com/#/person/1", "name": "Dana",
         "sameAs": ["https://www.linkedin.com/in/dana"]},
    ]}
    _, detail = content.expertise(_doc(graph))
    assert "author_profile" in detail["present"] and detail["byline"] == "Dana"


def test_an_article_nested_as_the_main_entity_still_names_its_author():
    page = {"@type": "WebPage", "mainEntity": {"@type": "BlogPosting", "headline": "h", "author": AUTHOR}}
    assert content.expertise(_doc(FOUNDER_GRAPH, page))[0] == 25


def test_a_commenter_is_not_the_author():
    post = {"@type": "BlogPosting", "headline": "h",
            "comment": [{"@type": "Comment", "author": {"@type": "Person", "name": "Reader", "jobTitle": "Critic"}}]}
    _, detail = content.expertise(_doc(post))
    assert "credentials" in detail["missing"] and detail["byline"] is None


def test_the_byline_detail_names_who_was_credited():
    """`byline: null` sat beside `present: [byline]` when the name came from markup."""
    _, detail = content.expertise(_doc({"@type": "BlogPosting", "headline": "h", "author": AUTHOR}))
    assert "byline" in detail["present"] and detail["byline"] == "Isabella Edwards"
    _, detail = content.expertise(_doc(meta='<meta name="author" content="Meta Name">'))
    assert detail["byline"] == "Meta Name"
