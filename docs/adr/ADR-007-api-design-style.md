# ADR-007: API Design Style — REST over GraphQL

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Before designing API endpoints, the communication style between frontend and backend must be decided. Two primary options were evaluated: REST and GraphQL.

This decision affects how the frontend requests data, how the backend structures responses, and the overall implementation complexity.

## Decision

**Use REST (Representational State Transfer).**

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| **REST (chosen)** | FastAPI native support + automatic OpenAPI docs, low implementation complexity, industry standard for public APIs | Fixed response shape per endpoint |
| GraphQL | Frontend requests exactly the fields it needs, flexible for complex data combinations | High implementation complexity, additional tooling required, learning curve |
| gRPC | High performance for service-to-service communication | Cannot be used directly from a browser |

## Why REST is Sufficient for Satlas

Each UI view maps cleanly to a single REST endpoint:

| View | Endpoint |
|---|---|
| Globe (all satellites) | `GET /satellites` |
| Country view | `GET /satellites/overhead/{country_code}` |
| Pass history | `GET /passes/{country_code}?start=&end=` |

GraphQL's primary advantage — letting the client specify exactly which fields to return — is not needed here. Satellite position calculation is handled client-side via satellite.js (per ADR-005), so the backend serves TLE data rather than computed positions. Response structures are simple and predictable.

## Security Note

API URLs are visible in the browser's Network tab by design. This is not a concern for Satlas because:

- Public API endpoints are intentionally open (rate-limited via Cloudflare)
- Protected endpoints require a JWT token — the URL alone is insufficient to access data
- CORS restricts browser-originated requests to the Vercel frontend domain
- HTTPS encrypts data in transit

## Consequences

- FastAPI generates OpenAPI (Swagger) documentation automatically — no additional tooling needed
- All endpoints follow REST conventions: URL represents a resource, HTTP method represents the action
- Frontend and backend communicate over HTTP regardless of monorepo structure — they are always separate runtimes
- If data requirements become significantly more complex in a future phase, GraphQL can be adopted incrementally for specific endpoints

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
