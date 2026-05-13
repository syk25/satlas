import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Emit dist/index-ko.html as a copy of dist/index.html with OG tags swapped
// to the Korean variant. Middleware (frontend/middleware.ts) rewrites the root
// path to /index-ko.html when x-vercel-ip-country === 'KR'.
function emitKoreanHtml() {
  return {
    name: 'emit-korean-html',
    apply: 'build' as const,
    closeBundle() {
      const distDir = path.resolve(__dirname, 'dist')
      const src = path.join(distDir, 'index.html')
      if (!fs.existsSync(src)) return
      const html = fs.readFileSync(src, 'utf-8')
      const koHtml = html
        .replace(/\/og-image\.png/g, '/og-image-ko.png')
        .replace(
          /property="og:locale" content="en_US"/,
          'property="og:locale" content="ko_KR"'
        )
        .replace(
          /property="og:locale:alternate" content="ko_KR"/,
          'property="og:locale:alternate" content="en_US"'
        )
      fs.writeFileSync(path.join(distDir, 'index-ko.html'), koHtml)
    },
  }
}

export default defineConfig({
  plugins: [react(), emitKoreanHtml()],
  build: {
    target: 'esnext',
  },
  worker: {
    format: 'es',
  },
})
