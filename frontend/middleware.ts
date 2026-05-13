import { rewrite, next } from '@vercel/edge'

// Run on all paths except API routes and static assets (anything with a dot in
// the last path segment). SPA routes like /, /about, /dashboard all return the
// same index.html, so we rewrite at the HTML response boundary to swap in the
// Korean OG tags for KR-geo requests.
export const config = {
  matcher: '/((?!api/|assets/|.*\\..*).*)',
}

export default function middleware(request: Request) {
  const country = request.headers.get('x-vercel-ip-country')
  if (country === 'KR') {
    const url = new URL(request.url)
    url.pathname = '/index-ko.html'
    return rewrite(url)
  }
  return next()
}
