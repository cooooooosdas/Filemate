import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createReadStream, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'

const visionRoot = dirname(createRequire(import.meta.url).resolve('@mediapipe/tasks-vision'))
const visionFiles = ['vision_wasm_internal.js', 'vision_wasm_internal.wasm', 'vision_wasm_nosimd_internal.js', 'vision_wasm_nosimd_internal.wasm', 'vision_wasm_module_internal.js', 'vision_wasm_module_internal.wasm']

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), {
    name: 'local-interview-vision-assets',
    configureServer(server) {
      server.middlewares.use('/interview-vision/wasm', (request, response, next) => {
        const filename = request.url?.split('?')[0]?.replace(/^\//, '') || ''
        if (!visionFiles.includes(filename)) return next()
        response.setHeader('Content-Type', filename.endsWith('.wasm') ? 'application/wasm' : 'text/javascript')
        createReadStream(join(visionRoot, 'wasm', filename)).pipe(response)
      })
    },
    generateBundle() {
      for (const filename of visionFiles) this.emitFile({ type: 'asset', fileName: 'interview-vision/wasm/' + filename, source: readFileSync(join(visionRoot, 'wasm', filename)) })
    }
  }],
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ['**/src-tauri/**'],
    },
    proxy: {
      '^/ai/contexts': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/process': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        ws: true,
      },
      '^/sessions': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        ws: true,
      },
      '^/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        ws: true,
      },
      '^/settings': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ai/summarize': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ai/knowledge-cards': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ai/questions': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ai/notes': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ai/study-plan': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ai/chat': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ai/learning/sessions': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/knowledge': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        ws: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/quiz': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/wrongbook': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/interview/questions': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/interviews': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/analytics': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/review': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/study-plans': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/evaluation': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '^/goals': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/trust': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/agents': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
