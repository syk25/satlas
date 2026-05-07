import react from '@vitejs/plugin-react'
import cesium from 'vite-plugin-cesium'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), cesium()],
})
