# The AI crawler tokens, and what each one gates

The list below is generated from `data/ai_crawlers.json` and carries each operator's
own documentation URL, so every row here is checkable rather than folklore.

The column that matters is **critical**. It marks a token whose refusal directly costs
visibility in an answer surface, as opposed to refusing to be training data. Those are
separate decisions and a site can reasonably make them differently.

<!-- generated:crawlers:begin -->
| Token | Operator | Purpose | Critical | Gates |
|---|---|---|---|---|
| `GPTBot` | [OpenAI](https://platform.openai.com/docs/bots) | model training | no | presence in future OpenAI model weights |
| `OAI-SearchBot` | [OpenAI](https://platform.openai.com/docs/bots) | search index | **yes** | appearing in ChatGPT search results |
| `ChatGPT-User` | [OpenAI](https://platform.openai.com/docs/bots) | user-triggered browsing | **yes** | ChatGPT reading the page when a user links it |
| `PerplexityBot` | [Perplexity](https://docs.perplexity.ai/guides/bots) | search index | **yes** | being cited in Perplexity answers |
| `Perplexity-User` | [Perplexity](https://docs.perplexity.ai/guides/bots) | user-triggered browsing | **yes** | Perplexity opening the page for a user |
| `ClaudeBot` | [Anthropic](https://support.anthropic.com/en/articles/8896518) | model training | no | presence in future Claude model weights |
| `Claude-SearchBot` | [Anthropic](https://support.anthropic.com/en/articles/8896518) | search index | **yes** | appearing in Claude's search results |
| `Claude-User` | [Anthropic](https://support.anthropic.com/en/articles/8896518) | user-triggered browsing | **yes** | Claude reading the page when a user links it |
| `Google-Extended` | [Google](https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers) | Gemini and Vertex grounding | **yes** | use as a grounding source for Gemini |
| `Googlebot` | [Google](https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers) | search index | **yes** | Google Search and AI Overviews, both of which source from the index |
| `Bingbot` | [Microsoft](https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0) | search index | **yes** | Bing and Copilot, which source from the Bing index |
| `Applebot` | [Apple](https://support.apple.com/en-us/119829) | search index | no | Siri and Spotlight suggestions |
| `Applebot-Extended` | [Apple](https://support.apple.com/en-us/119829) | model training | no | use in Apple foundation models |
| `meta-externalagent` | [Meta](https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/) | model training and indexing | no | use by Meta AI |
| `Amazonbot` | [Amazon](https://developer.amazon.com/amazonbot) | search index | no | Alexa answers |
| `CCBot` | [Common Crawl](https://commoncrawl.org/ccbot) | open web corpus | no | inclusion in the corpus most open models train on |

*Generated from `data/ai_crawlers.json` at data_version 2026.09.*
<!-- generated:crawlers:end -->

## How to talk about a blocked token

**A blocked training token is not a finding.** Many organisations refuse training
deliberately, and reversing that is a policy decision, not a technical fix. If the
audit shows training tokens blocked and search tokens allowed, say that the site has
drawn the line in a coherent place.

**A blocked search token is a decision to be absent.** Say it plainly: with
`OAI-SearchBot` disallowed, the site cannot appear in ChatGPT's search results,
regardless of how good its content is. That may still be the right choice for an
intranet or a private beta. It is rarely the right choice by accident, and it usually
is an accident.

## The failure that looks like nothing

A robots.txt returning 5xx is worse than one that disallows everything, because it
looks fine in a browser. RFC 9309 section 2.3.1.4 tells compliant crawlers to treat an
unreachable robots.txt as a complete disallow. `technical.crawler_access` scores it
zero and `detail.robots_status` names the code.

A 4xx is the opposite and is fine: section 2.3.1.3 makes an unavailable robots.txt
mean everything is allowed.
