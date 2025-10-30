import { fireEvent } from '@testing-library/dom';
import { describe, expect, it, vi } from 'vitest';

import { initHeader } from '../webbed_duck/static/assets/wd/header.js';

describe('initHeader', () => {
  const baseHeader = () => {
    document.body.innerHTML = `
      <header class="wd-top" data-wd-top data-hidden="false" data-collapsed="false">
        <div class="wd-top-inner">
          <div class="wd-top-actions">
            <button
              type="button"
              class="wd-top-button wd-top-button--ghost"
              data-wd-theme-toggle
              data-dark-label="Use dark theme"
              data-light-label="Use light theme"
              data-system-label="System theme ({theme})"
              aria-pressed="mixed"
            >System theme (light)</button>
            <button
              type="button"
              class="wd-top-button"
              data-wd-top-toggle
              data-hide-label="Hide header"
              data-show-label="Show header"
              aria-expanded="true"
            >Hide header</button>
            <button
              type="button"
              class="wd-top-button"
              data-wd-filters-toggle
              data-hide-label="Hide filters"
              data-show-label="Show filters"
              aria-expanded="true"
            >Hide filters</button>
          </div>
          <div class="wd-top-sections">
            <div class="wd-filters" data-wd-filters id="wd-filters"></div>
          </div>
        </div>
      </header>
    `;

    const header = document.querySelector('[data-wd-top]') as HTMLElement;
    Object.defineProperty(header, 'getBoundingClientRect', {
      value: () => ({ height: 120 } as DOMRect),
    });
    return header;
  };

  it('sets the top offset and toggles collapse state', () => {
    const header = baseHeader();
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });

    initHeader(header);

    expect(header.dataset.wdHeaderInit).toBe('1');
    expect(document.documentElement.style.getPropertyValue('--wd-top-offset')).toBe('120px');

    const toggleTop = header.querySelector('[data-wd-top-toggle]') as HTMLButtonElement;
    fireEvent.click(toggleTop);
    expect(header.getAttribute('data-collapsed')).toBe('true');
    expect(toggleTop).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(toggleTop);
    expect(header.getAttribute('data-collapsed')).toBe('false');
    expect(toggleTop).toHaveAttribute('aria-expanded', 'true');

    raf.mockRestore();
  });

  it('toggles filters visibility and persists theme preference', () => {
    const header = baseHeader();
    const filters = header.querySelector('[data-wd-filters]') as HTMLElement;
    const toggleFilters = header.querySelector('[data-wd-filters-toggle]') as HTMLButtonElement;
    const themeToggle = header.querySelector('[data-wd-theme-toggle]') as HTMLButtonElement;

    initHeader(header);

    expect(filters.hasAttribute('hidden')).toBe(false);
    fireEvent.click(toggleFilters);
    expect(filters.hasAttribute('hidden')).toBe(true);
    expect(toggleFilters).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(themeToggle);
    expect(document.documentElement.dataset.wdTheme).toBe('dark');
    expect(themeToggle).toHaveAttribute('aria-pressed', 'true');
    expect(themeToggle.textContent).toContain('Use light theme');
    expect(window.localStorage.getItem('wd-theme')).toBe('dark');

    themeToggle.dispatchEvent(new MouseEvent('click', { bubbles: true, altKey: true }));
    expect(document.documentElement.dataset.wdTheme).toBeUndefined();
    expect(themeToggle).toHaveAttribute('aria-pressed', 'mixed');
    expect(themeToggle.textContent).toContain('System theme');
    expect(window.localStorage.getItem('wd-theme')).toBeNull();
  });
});
