// Copies the Silero VAD model, its audio worklet and the onnxruntime wasm
// into public/vad so the browser can load them at runtime (served locally,
// no CDN: the app must work offline).
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'public', 'vad')
mkdirSync(out, { recursive: true })

const files = [
  'node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx',
  'node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js',
  'node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm',
  'node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs',
]
for (const f of files) copyFileSync(join(root, f), join(out, f.split('/').pop()))
console.log(`copied ${files.length} VAD assets to public/vad`)
