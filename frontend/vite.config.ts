import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const apiTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [
    react(),
    {
      // dev 下把 /m/* 重写到 /mobile.html，与生产 nginx 行为一致
      name: 'mobile-spa-rewrite',
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          if (req.url && (req.url === '/m' || req.url.startsWith('/m/') || req.url.startsWith('/m?'))) {
            req.url = '/mobile.html'
          }
          next()
        })
      },
    },
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        secure: false,
      },
      '/uploads': {
        target: apiTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        mobile: path.resolve(__dirname, 'mobile.html'),
      },
    },
  },
})
