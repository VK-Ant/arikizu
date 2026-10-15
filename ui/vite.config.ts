import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    proxy: {
      // Dev-mode: proxy API calls to the running arikizu runtime.
      '/api': 'http://127.0.0.1:7000',
    },
  },
});
