export const config = {
  runtime: 'edge',
}

export default function handler(request: Request): Response {
  const country = request.headers.get('x-vercel-ip-country')
  return new Response(JSON.stringify({ country: country ?? null }), {
    headers: {
      'content-type': 'application/json',
      'cache-control': 'private, max-age=300',
    },
  })
}
