# Type requirements and worked examples

Requirements come from `data/schema_requirements.json`, derived from
[schema.org type pages](https://schema.org/docs/schemas.html) and
[Google's structured data documentation](https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data),
whose [search gallery](https://developers.google.com/search/docs/appearance/structured-data/search-gallery)
lists the types Google acts on. Required properties are what make a
node legal; recommended are what make it useful.

<!-- generated:schema-types:begin -->
| Type | Required | Recommended |
|---|---|---|
| `Article` | `headline` | `author`, `datePublished`, `dateModified`, `image`, `publisher` |
| `BlogPosting` | `headline` | `author`, `datePublished`, `dateModified`, `publisher` |
| `BreadcrumbList` | `itemListElement` | - |
| `Event` | `name`, `startDate` | `location`, `endDate`, `offers` |
| `FAQPage` | `mainEntity` | - |
| `HowTo` | `name`, `step` | `totalTime`, `supply`, `tool` |
| `LocalBusiness` | `name`, `address` | `telephone`, `openingHours`, `url`, `geo` |
| `NewsArticle` | `headline` | `author`, `datePublished`, `dateModified`, `publisher` |
| `Organization` | `name` | `url`, `logo`, `sameAs`, `description` |
| `Person` | `name` | `url`, `sameAs`, `jobTitle` |
| `Product` | `name` | `offers`, `image`, `description`, `brand`, `aggregateRating` |
| `Recipe` | `name` | `recipeIngredient`, `recipeInstructions`, `image` |
| `SoftwareApplication` | `name` | `applicationCategory`, `offers`, `operatingSystem` |
| `VideoObject` | `name` | `description`, `thumbnailUrl`, `uploadDate` |
| `WebPage` | - | `name`, `description`, `speakable` |
| `WebSite` | `name` | `url`, `potentialAction` |

*Generated from `data/schema_requirements.json` at data_version 2026.09.*
<!-- generated:schema-types:end -->

## The publisher block, which most sites are missing

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "https://example.com/#organization",
  "name": "Example Ltd",
  "url": "https://example.com",
  "logo": "https://example.com/logo.png",
  "description": "One sentence on what the company does.",
  "sameAs": [
    "https://en.wikipedia.org/wiki/Example_Ltd",
    "https://www.wikidata.org/wiki/Q12345",
    "https://github.com/example"
  ]
}
```

`sameAs` is the property that does the work. It is how an engine ties this site to an
entity it already knows about. An Organization node without it says "a company exists"
and stops there.

The `@id` matters too: with it, an Article can reference the publisher rather than
restating it, and the two nodes are understood as the same entity.

## An article that can be dated and attributed

```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "How server-side rendering affects AI crawlers",
  "datePublished": "2026-03-04",
  "dateModified": "2026-08-19",
  "author": { "@type": "Person", "name": "Dana Okonkwo" },
  "publisher": { "@id": "https://example.com/#organization" }
}
```

Two rules that are easy to get wrong:

- **Visible and structured have to agree.** A `datePublished` in JSON-LD that no reader
  can see is a discrepancy an engine may discount.
- **A `dateModified` that moves on every deploy is worse than no date.** It tells an
  engine the page changed when the text did not, and it trains it to ignore the field.

## Types that answer a question directly

`schema.breadth` looks for these because they map onto the shape of an answer rather
than describing the page:

`FAQPage` - `HowTo` - `QAPage` - `BreadcrumbList` - `Product` - `Event` - `Recipe` -
`VideoObject` - `SoftwareApplication` - `LocalBusiness`

Add them only where the content genuinely fits. Marking a page `FAQPage` when it has
no questions on it is a misdescription, and misdescription is the one thing structured
data cannot survive.
