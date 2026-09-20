"""RFC 9309 matrix.

These are the cases where robots parsers quietly disagree with each other, so
each one names the section it comes from.
"""

from __future__ import annotations

import pytest

from geo_audit.lib import robots as robots_lib
from tests.fixture_server import Reply

from geo_audit.lib.headers import PRODUCT_TOKEN

UA = PRODUCT_TOKEN


def parse(text: str):
    return robots_lib.parse(text, source_url="http://fixture/robots.txt")


def test_empty_file_allows_everything():
    assert parse("").allows(UA, "/anything")


def test_disallow_slash_blocks_everything():
    rules = parse("User-agent: *\nDisallow: /")
    assert not rules.allows(UA, "/")
    assert not rules.allows(UA, "/deep/path")


def test_empty_disallow_value_allows_everything():
    """Section 2.2.2: an empty Disallow is not a rule."""
    rules = parse("User-agent: *\nDisallow:")
    assert rules.allows(UA, "/anything")


def test_longest_match_wins():
    rules = parse("User-agent: *\nDisallow: /docs\nAllow: /docs/public")
    assert not rules.allows(UA, "/docs/private")
    assert rules.allows(UA, "/docs/public/page")


def test_allow_wins_an_exact_length_tie():
    """Section 2.2.2: the least restrictive rule wins."""
    rules = parse("User-agent: *\nDisallow: /x\nAllow: /x")
    assert rules.allows(UA, "/x")


def test_wildcards_and_end_anchor():
    rules = parse("User-agent: *\nDisallow: /*.pdf$")
    assert not rules.allows(UA, "/files/report.pdf")
    assert rules.allows(UA, "/files/report.pdf.html")


def test_specific_group_beats_wildcard_group():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n"
    rules = parse(text)
    assert rules.allows("GPTBot", "/page")
    assert not rules.allows("SomeOtherBot", "/page")


def test_longest_agent_token_wins_when_several_match():
    text = (
        "User-agent: Claude\nDisallow: /\n\n"
        "User-agent: ClaudeBot\nAllow: /\n"
    )
    rules = parse(text)
    assert rules.allows("ClaudeBot", "/page")


def test_agent_matching_is_case_insensitive():
    rules = parse("User-agent: gptbot\nDisallow: /")
    assert not rules.allows("GPTBot", "/page")


def test_consecutive_user_agent_lines_share_one_group():
    text = "User-agent: A\nUser-agent: B\nDisallow: /no\n"
    rules = parse(text)
    assert not rules.allows("A", "/no")
    assert not rules.allows("B", "/no")


def test_a_new_user_agent_after_rules_starts_a_new_group():
    text = "User-agent: A\nDisallow: /a\nUser-agent: B\nDisallow: /b\n"
    rules = parse(text)
    assert not rules.allows("A", "/a")
    assert rules.allows("A", "/b")
    assert not rules.allows("B", "/b")
    assert rules.allows("B", "/a")


def test_comments_and_blank_lines_are_ignored():
    text = "# a comment\n\nUser-agent: *   # trailing\nDisallow: /no  # here\n"
    rules = parse(text)
    assert not rules.allows(UA, "/no")


def test_unknown_fields_are_ignored():
    rules = parse("User-agent: *\nRequest-rate: 1/10\nDisallow: /no\n")
    assert not rules.allows(UA, "/no")


def test_crawl_delay_is_read_per_group():
    rules = parse("User-agent: *\nCrawl-delay: 2.5\nDisallow: /no\n")
    assert rules.crawl_delay_for(UA) == 2.5


def test_sitemaps_are_collected_outside_any_group():
    rules = parse("Sitemap: https://example.com/sitemap.xml\nUser-agent: *\nDisallow:\n")
    assert rules.sitemaps == ["https://example.com/sitemap.xml"]


def test_percent_encoded_paths_match_their_decoded_form():
    rules = parse("User-agent: *\nDisallow: /a b\n")
    assert not rules.allows(UA, "/a%20b")


# --- status handling, section 2.3.1 ---------------------------------------


def test_404_means_everything_is_allowed(serve):
    server = serve({"/robots.txt": Reply(status=404, body="nope")})
    rules = robots_lib.load(f"{server.url}/page", allow_private=True)
    assert rules.unavailable is True
    assert rules.allows(UA, "/anything")


def test_500_means_everything_is_disallowed(serve):
    """Section 2.3.1.4: an unreachable robots.txt is a complete disallow."""
    server = serve({"/robots.txt": Reply(status=500, body="boom")})
    rules = robots_lib.load(f"{server.url}/page", allow_private=True)
    assert rules.unreachable is True
    assert not rules.allows(UA, "/anything")


def test_robots_redirects_are_followed(serve):
    server = serve(
        {
            "/robots.txt": Reply(status=302, headers={"Location": "/real-robots.txt"}),
            "/real-robots.txt": Reply(
                body="User-agent: *\nDisallow: /no\n", content_type="text/plain"
            ),
        }
    )
    rules = robots_lib.load(f"{server.url}/page", allow_private=True)
    assert not rules.allows(UA, "/no")


def test_robots_is_looked_up_at_the_origin_root():
    assert (
        robots_lib.robots_url_for("https://example.com/deep/page?x=1")
        == "https://example.com/robots.txt"
    )
    assert robots_lib.robots_url_for("http://example.com:8080/x") == "http://example.com:8080/robots.txt"


def test_access_matrix_is_ordered_by_the_input_list():
    rules = parse("User-agent: GPTBot\nDisallow: /\n")
    rows = robots_lib.access_matrix(rules, ["Googlebot", "GPTBot", "ClaudeBot"], "/page")
    assert [row["agent"] for row in rows] == ["Googlebot", "GPTBot", "ClaudeBot"]
    assert [row["allowed"] for row in rows] == [True, False, True]


@pytest.mark.parametrize("path", ["/", "/page", "/deep/page.html"])
def test_our_own_token_is_checked_separately_from_the_product_feature(path):
    rules = parse(f"User-agent: {PRODUCT_TOKEN}\nDisallow: /\n")
    assert not robots_lib.self_allows(rules, path)
    assert rules.allows("GPTBot", path)
