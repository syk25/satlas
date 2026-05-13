# ADR-025: IP-geo language pick + per-country OG image variants

**Status**: Superseded (2026-05-13)
**Date**: 2026-05-13

> **2026-05-13 update.** The implementation shipped (Vercel Edge Function
> at `frontend/api/geo.ts`, middleware at `frontend/middleware.ts`, Vite
> plugin emitting `dist/index-ko.html`) was never recognised by the
> Vercel deployment — `https://satlas.space/api/geo` returned 404 in
> prod, which silently broke both the first-visit language pick and the
> KR-geo OG rewrite. The root cause is most likely a project-root /
> framework-preset interaction in Vercel that we did not chase down.
>
> Rather than debug the Vercel side, the decision was rolled back: the
> Edge Function, middleware, Vite plugin, `og-image-ko.{svg,png}`, the
> `@vercel/edge` dependency, and the geo-fetch block in `src/i18n.ts`
> were all removed. Language detection now falls back to the standard
> `i18next-browser-languagedetector` chain (localStorage → navigator)
> with no IP component. The English/Korean README pair remains as the
> visible signal that the site speaks both languages.
>
> The body below is preserved as the original decision record. If
> IP-aware language or OG variants are revisited, this ADR is the
> starting point — the trade-off table and alternatives are still the
> right framing; only the Vercel-recognition problem needs solving
> first.

---

## Context

Satlas now ships as a Vite SPA on Vercel, served as a single static
`dist/index.html` with two locale bundles (`en`, `ko`) loaded at runtime
by `react-i18next`. Phase 1 of the public launch checklist required two
related improvements:

1. **Default language pick.** The previous setup used
   `i18next-browser-languagedetector` with its default chain
   (localStorage → navigator → fallback `en`). That worked for users
   whose browser locale matched their actual location, but mismatched
   for the two cases we expected to be common at launch:

   - Korean residents using English-locale browsers (e.g. dev-focused
     users with `en-US` browsers) saw English text despite being the
     target audience.
   - Overseas Koreans with `ko-KR` browsers saw Korean even when the
     surrounding audience was English-first.

2. **Locale-correct social preview.** SPAs cannot vary `<meta>` tags
   per visitor without server-side help — the static `index.html` ships
   with one `og:image` URL and crawlers (KakaoTalk, Slack, Twitter,
   etc.) never execute JavaScript, so client-side meta swaps are
   invisible to them. Sharing a Satlas link in a Korean chat showed
   English OG copy, which undercut the audience-aware UX of the rest
   of the site.

A heavier framework migration (Next.js, Astro, etc.) would solve both
out of the box, but the entire frontend is two engineers' weekends of
work — flipping the framework to fix a launch-time polish item is the
wrong unit of action. We needed something narrow.

---

## Decision

**1. Use Vercel's edge-injected geo header as the language signal.**

Every request to a Vercel deployment carries `x-vercel-ip-country`,
populated from the edge's MaxMind GeoIP lookup at no extra cost. A
single Edge Function (`frontend/api/geo.ts`) reflects the header back
to the client:

```ts
export const config = { runtime: 'edge' }

export default function handler(request: Request): Response {
  const country = request.headers.get('x-vercel-ip-country')
  return new Response(JSON.stringify({ country: country ?? null }), {
    headers: { 'content-type': 'application/json',
               'cache-control': 'private, max-age=300' },
  })
}
```

The Edge Function exists so the SPA can read the header without a
custom transport — `fetch('/api/geo')` returns the country reliably,
including during local development (where it returns `null` and the
client falls back to navigator-based detection).

**2. Layered language detection in `src/i18n.ts`.**

```ts
detection: { order: ['localStorage', 'navigator'], caches: ['localStorage'] }
```

`localStorage` wins (so an explicit user toggle is permanent) and
`navigator` is the synchronous fallback (so first paint is in a
sensible language). After init, on the *first* visit only —
`!localStorage.getItem('i18nextLng')` — we fetch `/api/geo` and call
`i18n.changeLanguage('ko')` if `country === 'KR'`, otherwise `'en'`.
The call is best-effort: on network failure or dev (no `/api/geo`)
the navigator-based guess from init stays. Once any language has been
resolved (geo or toggle), `caches: ['localStorage']` persists it and
the geo fetch is skipped on subsequent visits.

The async geo step means a Korean visitor on an English browser sees
roughly 100 ms of English text before the swap. The trade is
acceptable for a once-per-user flicker; the alternative (blocking the
initial render on the fetch) would have been worse for the much more
common returning-visitor path.

**3. Build-time emission of `dist/index-ko.html`.**

A Vite plugin (`emitKoreanHtml` in `vite.config.ts`) reads
`dist/index.html` at `closeBundle`, replaces three string patterns,
and writes the result as `dist/index-ko.html`:

```ts
.replace(/\/og-image\.png/g, '/og-image-ko.png')
.replace(/property="og:locale" content="en_US"/, ...'ko_KR'...)
.replace(/property="og:locale:alternate" content="ko_KR"/, ...'en_US'...)
```

The global regex on the image URL catches both `og:image` and
`twitter:image` in a single substitution. Both files share the same
`<script type="module" src="/assets/index-*.js" />` reference, so the
SPA bundle is identical between locales — only the head metadata
differs.

We picked build-time HTML duplication over runtime body rewriting
deliberately:

- Edge middleware that streams + transforms the HTML response would
  re-pay the CPU cost on every request and complicate caching.
- Static HTML files hit Vercel's CDN cache directly with no Edge
  cold-start tax for the 95%+ of visitors who don't need rewriting
  (only non-KR visitors get the default route through the CDN).

**4. Edge middleware rewrites `/` (and SPA fallbacks) to `index-ko.html`
for KR visitors.**

```ts
// frontend/middleware.ts
import { rewrite, next } from '@vercel/edge'

export const config = { matcher: '/((?!api/|assets/|.*\\..*).*)' }

export default function middleware(request: Request) {
  const country = request.headers.get('x-vercel-ip-country')
  if (country === 'KR') {
    const url = new URL(request.url)
    url.pathname = '/index-ko.html'
    return rewrite(url)
  }
  return next()
}
```

The matcher excludes everything containing a `.` (i.e. static assets
like `/og-image.png`, `/favicon.svg`, the bundled JS/CSS) and the
`/api/` and `/assets/` prefixes. What's left is `/`, `/about`,
`/dashboard` — every path that SPA fallback would serve as
`index.html`, which is now `index-ko.html` for Korean visitors. The
SPA's client-side router runs the same way against either HTML; only
the head differs.

**5. Two static OG images.**

`og-image.png` (English copy) and `og-image-ko.png` (Korean copy),
both 1200×630 PNGs generated from hand-written SVG via
`rsvg-convert` at build-author time, committed under
`frontend/public/`. The Korean variant uses Apple SD Gothic Neo
(system font) and the same illustration; only the wordmark, tagline,
and caption strings are localised.

We did not adopt a runtime image generation service (`@vercel/og`,
Cloudinary, etc.) because two static PNGs cover every locale we
support today and the dynamic variant would mean paying for the
edge runtime on every share-link unfurl, which is most of the
traffic that ever touches an OG URL.

---

## Alternatives Considered

### A. Keep browser-language-only detection
This is what we had. Rejected because the user explicitly identified
the two mismatch cases (Korean browser overseas / English browser in
Korea) and asked for IP-based fallback. The implementation cost of
adding the geo fetch is one Edge Function plus ~10 lines in
`i18n.ts` — the lowest viable upgrade over what we shipped.

### B. SSR / SSG migration (Next.js, Astro, Remix)
Solves both problems natively: per-locale prerendering, per-request
header access in `getServerSideProps` / loaders, automatic per-route
metadata. Rejected as out of scope — the SPA is already deployed
and the surface area to migrate (Cesium, Leaflet, satellite.js,
i18next, the worker pool) is large enough that this would have been
a multi-week project. ADR-014 explicitly picked Vite SPA + Vercel
static for the trade we are now paying; this ADR pays it without
reversing it.

### C. Bilingual OG image (one shared PNG with both languages)
Fits a single static file, no middleware needed. Rejected: the
intended audience for the image is a chat preview ~600px wide, and
stacking English and Korean copy in that frame leaves both at half
the legibility budget. Worse, the "this site speaks your language"
signal — which is the only reason we cared about locale-aware OG in
the first place — is diluted when half the text is in the other
language.

### D. Client-side `<meta>` tag injection
React Helmet or document.head writes from `useEffect` would update
the live DOM after the SPA boots. Rejected: every social-preview
crawler reads the static HTML response and never runs JS, so the
correction would be invisible to exactly the audience it exists
to serve.

### E. Vercel Edge middleware that rewrites HTML body
A middleware that fetched the base `index.html` and string-replaced
the OG tags on every request. Equivalent end state to (3) + (4) but
without the build-time duplication. Rejected because it re-runs CPU
work on every request, complicates response caching (each variant
needs a Vary header or per-country cache key), and is slower than
serving two static files from the CDN's existing path cache.

---

## Consequences

**Positive**

- Korean visitors see Korean copy from first paint on returning
  visits (localStorage cached) and after a ~100 ms swap on first
  visit. English visitors see English unchanged.
- A KR-geo link share into KakaoTalk / Slack / Twitter previews
  the Korean OG image, with the tagline pulled from `app.tagline`
  (the same string the site header uses), so the preview and the
  landing page agree visually and verbally.
- The mechanism extends to new locales by adding (a) a country
  branch in `i18n.ts`, (b) a new `og-image-{lang}.png`, (c) a
  replacement target in the Vite plugin, and (d) a country branch
  in middleware. No framework change required.
- Vercel's Edge Function and middleware quotas (1M req / 1M exec
  per month on Hobby) cover roughly 30K daily visits with headroom.
  At our current scale (low hundreds / day) this is free.

**Negative**

- Dev environments don't reproduce the KR path. Running `vite` locally
  never hits `/api/geo` (it 404s) or the middleware, so the only place
  the full chain is exercised is staging or production. Visual
  inspection of the produced `dist/index-ko.html` is the cheapest
  pre-deploy check; the deploy itself is the only end-to-end verification.
- The system is Vercel-specific. `x-vercel-ip-country`,
  `@vercel/edge`'s `rewrite`, and the `middleware.ts` root convention
  are all Vercel features. Moving the frontend off Vercel (Cloudflare
  Pages, Netlify, self-host) means rewriting both the Edge Function
  and the middleware against the target's primitives. ADR-014's
  platform pick already documents Vercel as the chosen host; the
  coupling is consistent with that.
- The HTML variant is duplicated in source: every future `<head>`
  change has to land in `index.html` and be reflected in the Vite
  plugin's `.replace` patterns if it touches OG strings. Keeping the
  replace patterns terse and tied to `og:` / `twitter:` prefixes
  limits the maintenance surface, but it is not zero.
- First-visit Korean visitors with an English browser see a ~100 ms
  English flash before the swap. Acceptable for the once-per-user
  cost; would be unacceptable if it recurred on every page.

---

## Notes

- The matcher regex `/((?!api/|assets/|.*\\..*).*)` was tested against
  every current top-level path: `/`, `/about`, `/dashboard` match;
  `/api/geo`, `/og-image.png`, `/og-image-ko.png`, `/favicon.svg`,
  `/manifest.json`, `/apple-touch-icon.png`,
  `/android-chrome-{192,512}.png`, `/assets/*` do not. If a new
  extension-less route is added (e.g. `/privacy`), it is automatically
  picked up by the matcher and gets the same locale rewrite for free.
- The OG SVGs are kept under `public/og-image{,-ko}.svg` for
  re-generation. `rsvg-convert` is not invoked by the build — they
  are regenerated by hand on copy/design changes and the PNGs are
  committed.
- The geo fetch's `cache-control: private, max-age=300` keeps the
  browser from re-asking during a single session, which would happen
  if the user closed and reopened the tab quickly. It does not
  participate in the CDN cache (`private`), so two different visitors
  cannot accidentally read each other's country.
