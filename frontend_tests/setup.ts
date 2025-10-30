import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, vi } from 'vitest';

if (!globalThis.requestAnimationFrame) {
  globalThis.requestAnimationFrame = (cb: FrameRequestCallback): number => {
    cb(performance.now());
    return 0;
  };
}

if (!window.requestAnimationFrame) {
  Object.defineProperty(window, 'requestAnimationFrame', {
    configurable: true,
    writable: true,
    value: globalThis.requestAnimationFrame,
  });
}

if (!globalThis.cancelAnimationFrame) {
  globalThis.cancelAnimationFrame = () => {};
}

if (!window.cancelAnimationFrame) {
  Object.defineProperty(window, 'cancelAnimationFrame', {
    configurable: true,
    writable: true,
    value: globalThis.cancelAnimationFrame,
  });
}

beforeEach(() => {
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  delete (document.documentElement.dataset as Record<string, string | undefined>).wdTheme;
  try {
    window.localStorage.clear();
  } catch (error) {
    // Ignore environments without storage support
  }
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});
