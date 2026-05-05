# ADR-003: Disputed Territory Policy — Natural Earth + Visual Distinction

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Satlas displays satellite data over national territories using GeoJSON boundary data. Some territories are disputed between nations. Every boundary dataset carries an implicit geopolitical stance — true neutrality is not achievable.

The underlying data source (Natural Earth) follows broadly recognized international conventions but does not reflect all competing territorial claims.

This decision affects:
- Which regions appear as selectable countries in the UI
- How disputed borders are rendered
- Whether satellite data is available for contested regions
- The platform's legal and reputational exposure

## Decision

1. **Use Natural Earth as the sole boundary data source.** It is the open-source standard, well-maintained, and widely used by mapping tools globally.
2. **Mark disputed territories visually.** Contested borders are rendered with dashed lines or distinct styling. The UI does not silently imply a political position.
3. **Do not disable satellite queries for any region.** Restricting data in contested areas would directly undermine the platform's primary use case for security and defense researchers.
4. **Add an explicit disclaimer** in the README and UI acknowledging that boundary data follows Natural Earth conventions and does not represent a political position on any territorial dispute.

## Core Principle

**Internationally recognized boundaries take precedence over territorial claims made by force or unilateral declaration.**

Regions under military occupation that are internationally recognized as belonging to another state are displayed according to that international recognition, not the occupying state's claim.

## Specific Cases

| Territory | Natural Earth | Satlas Display | Rationale |
|---|---|---|---|
| Dokdo/Takeshima | South Korea | South Korea, no disputed marking | South Korea exercises control; South Korea does not recognize a dispute |
| Crimea | Ukraine | Ukraine | UN General Assembly affirms Ukrainian sovereignty |
| Donetsk, Luhansk, Zaporizhzhia, Kherson | Ukraine | Ukraine | UN-recognized Ukrainian territory despite Russian annexation declaration |
| Taiwan | Separate entity (TW) | Separate entity | Natural Earth standard; consistent with open-source mapping conventions |

**Note on Taiwan**: Following Natural Earth means Taiwan is displayed as a separate entity from China. This is consistent with how the majority of open-source mapping tools handle this case. Access from mainland China may be affected as a result — this tradeoff is accepted.

**Note on active conflict zones**: Visual distinction for active military conflicts (as opposed to territorial disputes) is out of scope for the initial release. This may be revisited as a future enhancement.

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| Natural Earth, no distinction | Simple, low maintenance | Silently implies political stances |
| **Natural Earth + visual distinction (chosen)** | Transparent, research-friendly | Requires disputed territory dataset |
| Disable queries for disputed regions | Reduces political exposure | Removes data most relevant to target users |
| Geo-targeted boundaries per user country | Maximally local accuracy | Unmanageable complexity, implies multiple political stances |

## Consequences

- Disputed territories are queryable — satellite data is available without restriction
- Boundary representation follows Natural Earth; the platform does not adjudicate territorial claims
- README and UI include a boundary disclaimer
- Disputed borders sourced from Natural Earth's `ne_10m_admin_0_disputed_areas` dataset for visual styling
- Access from mainland China may be limited due to Taiwan display policy

## Boundary Data Extensibility

MVP uses Natural Earth land polygons only (no maritime boundaries). The satellite-over-country intersection logic treats boundary polygons as interchangeable inputs — it does not depend on the data source. This allows maritime boundaries (e.g., territorial sea) to be added later as a data update without code changes.

Maritime boundary data (Marine Regions / VLIZ, CC-BY) was evaluated and deferred: the data source imposes a "scientific and research purposes" use restriction that creates ambiguity under a COSS commercial model, and the raw data may not be redistributed via API. If added in a future phase, the intersection engine requires no modification — only the polygon dataset changes.
