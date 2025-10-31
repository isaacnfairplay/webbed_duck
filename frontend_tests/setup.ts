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

  const observers: Array<{
    observe: ReturnType<typeof vi.fn>;
    unobserve: ReturnType<typeof vi.fn>;
    disconnect: ReturnType<typeof vi.fn>;
    takeRecords: ReturnType<typeof vi.fn>;
    trigger: (entry: IntersectionObserverEntry) => void;
  }> = [];

  Object.defineProperty(window, 'IntersectionObserver', {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation(
      (callback: IntersectionObserverCallback): IntersectionObserver => {
        const instance = {
          observe: vi.fn(),
          unobserve: vi.fn(),
          disconnect: vi.fn(),
          takeRecords: vi.fn().mockReturnValue([]),
          trigger(entry: IntersectionObserverEntry) {
            callback([entry], instance as unknown as IntersectionObserver);
          },
        };
        observers.push(instance);
        return instance as unknown as IntersectionObserver;
      },
    ),
  });

  (window as typeof window & { __wdIntersectionObservers?: typeof observers }).__wdIntersectionObservers = observers;
});

afterEach(() => {
  delete (window as typeof window & { __wdIntersectionObservers?: unknown }).__wdIntersectionObservers;
  vi.restoreAllMocks();
});
