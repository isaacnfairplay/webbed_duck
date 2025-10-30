import { fireEvent } from '@testing-library/dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { initMultiSelect } from '../webbed_duck/static/assets/wd/multi_select.js';

const OPTION_LABELS = ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel', 'India', 'Juliet'];

const buildMultiSelect = () => {
  const optionsMarkup = OPTION_LABELS.map((label, index) => {
    const value = `opt-${index + 1}`;
    const checked = index < 2 ? ' checked' : '';
    return `
      <li class="wd-multi-select-option" data-search="${label.toLowerCase()} ${value}">
        <label><input type="checkbox" value="${value}"${checked}/><span>${label}</span></label>
      </li>
    `;
  }).join('');

  const selectOptions = OPTION_LABELS.map((label, index) => {
    const value = `opt-${index + 1}`;
    const selected = index < 2 ? ' selected' : '';
    return `<option value="${value}"${selected}>${label}</option>`;
  }).join('');

  document.body.innerHTML = `
    <div class="wd-multi-select" data-wd-widget="multi">
      <button type="button" class="wd-multi-select-toggle" aria-expanded="false" aria-controls="panel-1">
        <span class="wd-multi-select-summary">Alpha, Bravo</span>
        <span class="wd-multi-select-caret" aria-hidden="true">▾</span>
      </button>
      <div class="wd-multi-select-panel" id="panel-1" hidden>
        <div class="wd-multi-select-search"><input type="search" placeholder="Filter options" aria-label="Filter options" autocomplete="off"/></div>
        <p class="wd-multi-select-hint">Selections stay checked as you filter.</p>
        <ul class="wd-multi-select-options">${optionsMarkup}</ul>
        <div class="wd-multi-select-actions"><button type="button" class="wd-multi-select-clear">Clear</button></div>
      </div>
      <select class="wd-multi-select-input" multiple data-placeholder="All values">
        ${selectOptions}
      </select>
    </div>
  `;

  const container = document.querySelector('.wd-multi-select') as HTMLElement;
  return container;
};

describe('initMultiSelect', () => {
  let originalInnerHeight: number;

  beforeEach(() => {
    originalInnerHeight = window.innerHeight;
  });

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(window, 'innerHeight', { value: originalInnerHeight, configurable: true });
  });

  it('synchronizes selected options and summary text', () => {
    const container = buildMultiSelect();
    const panel = container.querySelector('.wd-multi-select-panel') as HTMLElement;
    const summary = container.querySelector('.wd-multi-select-summary') as HTMLElement;
    const clear = container.querySelector('.wd-multi-select-clear') as HTMLButtonElement;
    const checkboxes = Array.from(container.querySelectorAll('input[type="checkbox"]')) as HTMLInputElement[];

    Object.defineProperty(window, 'innerHeight', { value: 960, configurable: true });
    initMultiSelect(container);

    expect(container.dataset.wdMultiInit).toBe('1');
    expect(summary.textContent).toBe('Alpha, Bravo');

    fireEvent.click(clear);
    expect(summary.textContent).toBe('All values');

    fireEvent.click(checkboxes[4]);
    expect(checkboxes[4].checked).toBe(true);
    expect(summary.textContent).toContain('Echo');

    // Panel height adapts based on visible options
    expect(container.style.getPropertyValue('--wd-multi-panel-max-height')).toBe('460px');

    vi.useFakeTimers();
    const toggle = container.querySelector('.wd-multi-select-toggle') as HTMLButtonElement;
    fireEvent.click(toggle);
    vi.runAllTimers();
    expect(panel.hidden).toBe(false);

    const search = container.querySelector('.wd-multi-select-search input') as HTMLInputElement;
    fireEvent.input(search, { target: { value: 'juliet' } });
    expect(container.style.getPropertyValue('--wd-multi-panel-max-height')).toBe('268px');

    fireEvent.input(search, { target: { value: 'alpha' } });
    expect(container.style.getPropertyValue('--wd-multi-panel-max-height')).toBe('268px');

    fireEvent.input(search, { target: { value: '' } });
    expect(container.style.getPropertyValue('--wd-multi-panel-max-height')).toBe('460px');
  });
});
