import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = { target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true, timeout: 1_200_000, proxyTimeout: 1_200_000 };
  const proxy = { '/api': target, '/docs': target, '/openapi.json': target };
  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 4173, strictPort: true, proxy },
  };
});
