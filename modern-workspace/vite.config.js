import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // Relative asset URLs so the build also works when mounted at /app.
  base: './',
  plugins: [react()],
})
