import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./frontend_tests/setup.ts'],
    include: ['frontend_tests/**/*.spec.{js,ts}'],
    css: {
      include: ['webbed_duck/static/assets/wd/**/*.css'],
    },
    coverage: {
      reporter: ['text', 'lcov'],
      include: ['webbed_duck/static/assets/wd/**/*.js'],
    },
  },
});
