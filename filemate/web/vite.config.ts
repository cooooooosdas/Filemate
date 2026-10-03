import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import ElementPlus from 'unplugin-element-plus/vite'
import { createReadStream, existsSync, readFileSync, readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'

const visionRoot = dirname(createRequire(import.meta.url).resolve('@mediapipe/tasks-vision'))
const elementPlusComponents = join(dirname(createRequire(import.meta.url).resolve('element-plus/package.json')), 'es/components')
const elementPlusStyles = readdirSync(elementPlusComponents, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && existsSync(join(elementPlusComponents, entry.name, 'style/css.mjs')))
  .map((entry) => `element-plus/es/components/${entry.name}/style/css`)
const apiTarget = process.env.VITE_API_URL || 'http://127.0.0.1:8001'
const visionFiles = ['vision_wasm_internal.js', 'vision_wasm_internal.wasm', 'vision_wasm_nosimd_internal.js', 'vision_wasm_nosimd_internal.wasm', 'vision_wasm_module_internal.js', 'vision_wasm_module_internal.wasm']

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), Components({
    dirs: [],
    dts: false,
    resolvers: [ElementPlusResolver({ importStyle: 'css', directives: true })],
  }), ElementPlus({}), {
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
  build: { manifest: true },
  optimizeDeps: {
    // 首次打开懒加载页面时，样式入口不应触发依赖重编译和路由中断。
    include: [...elementPlusStyles, '@mediapipe/tasks-vision', 'animejs/waapi'],
  },
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ['**/src-tauri/**'],
    },
    proxy: {
      '^/ai/contexts': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/process': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      '^/sessions': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      '^/api': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      '^/settings': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ai/summarize': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ai/knowledge-cards': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ai/questions': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ai/notes': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ai/study-plan': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ai/chat': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ai/learning/sessions': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/knowledge': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/quiz': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/wrongbook': {
        target: apiTarget,
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/interview/questions': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/interviews': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/analytics': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/review': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/study-plans': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/evaluation': {
        target: apiTarget,
        changeOrigin: true,
      },
      '^/goals': {
        target: apiTarget,
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/trust': {
        target: apiTarget,
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '^/agents': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
