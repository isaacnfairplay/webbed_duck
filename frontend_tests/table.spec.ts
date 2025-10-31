import { describe, expect, it } from 'vitest';

import { initTableHeader } from '../webbed_duck/static/assets/wd/table_header.js';

declare global {
  interface Window {
    __wdIntersectionObservers?: Array<{
      observe: (target: Element) => void;
      trigger: (entry: IntersectionObserverEntry) => void;
    }>;
  }
}

describe('initTableHeader', () => {
  it('shows the mini header when the table header scrolls out of view', () => {
    document.body.innerHTML = `
      <div class="wd-surface wd-surface--flush wd-table" data-wd-table>
        <div class="wd-table-mini" data-wd-table-mini hidden></div>
        <div class="wd-table-scroller">
          <table>
            <thead>
              <tr><th>Greeting</th><th>Count</th></tr>
            </thead>
            <tbody>
              <tr><td>Hello</td><td>1</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    `;

    const container = document.querySelector('[data-wd-table]');
    const mini = container?.querySelector('[data-wd-table-mini]');
    expect(container).toBeTruthy();
    expect(mini).toBeTruthy();

    initTableHeader(container as HTMLElement);

    const miniHeader = mini as HTMLElement;
    expect(miniHeader.dataset.wdTableInit).toBeUndefined();
    expect(container?.dataset.wdTableInit).toBe('1');
    const labels = miniHeader.querySelectorAll('.wd-table-mini-label');
    expect(labels).toHaveLength(2);
    expect(labels[0].textContent).toBe('Greeting');
    expect(labels[1].textContent).toBe('Count');

    const observers = window.__wdIntersectionObservers || [];
    expect(observers).toHaveLength(1);

    observers[0].trigger({
      isIntersecting: true,
      intersectionRatio: 1,
    } as IntersectionObserverEntry);
    expect(miniHeader.hidden).toBe(true);

    observers[0].trigger({
      isIntersecting: false,
      intersectionRatio: 0,
    } as IntersectionObserverEntry);
    expect(miniHeader.hidden).toBe(false);
  });
});
