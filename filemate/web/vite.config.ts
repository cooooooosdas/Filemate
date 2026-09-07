import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
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
