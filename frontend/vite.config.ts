import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { createReadStream, existsSync } from 'node:fs'
import { extname, join } from 'node:path'
import { defineConfig, type Plugin } from 'vite'

const MIME: Record<string, string> = {
  '.mjs': 'text/javascript',
  '.js': 'text/javascript',
  '.wasm': 'application/wasm',
  '.onnx': 'application/octet-stream',
}

// onnxruntime-web loads its wasm glue with a dynamic import() from /vad/.
// Vite's dev server rewrites such imports of /public files (`?import`) and
// refuses them, so serve these files raw before Vite's own middleware.
function serveVadAssets(): Plugin {
  return {
    name: 'serve-vad-assets',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = req.url?.split('?')[0] ?? ''
        if (!path.startsWith('/vad/')) return next()
        const file = join(__dirname, 'public', path)
        if (!existsSync(file)) return next()
        res.setHeader('Content-Type', MIME[extname(file)] ?? 'application/octet-stream')
        createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [serveVadAssets(), react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', ws: true },
    },
  },
})
