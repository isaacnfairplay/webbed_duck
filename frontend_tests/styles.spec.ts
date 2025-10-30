import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const readCss = (relativePath: string) =>
  fs.readFileSync(path.join(process.cwd(), relativePath), 'utf8');

describe('frontend styles', () => {
  it('declares theme tokens for light and dark modes', () => {
    const css = readCss('webbed_duck/static/assets/wd/layout.css');
    expect(css).toMatch(/:root,\s*:root\[data-wd-theme='light'\][^}]*--wd-color-bg: #f8fafc;/);
    expect(css).toMatch(/:root\[data-wd-theme='dark'\][^}]*--wd-color-bg: #0f172a;/);
    expect(css).toMatch(/@media\s*\(prefers-color-scheme: dark\)\s*{\s*:root:not\(\[data-wd-theme='light'\]\)/);
    expect(css).toMatch(/\.wd-top-button[^}]*background: var\(--wd-accent-soft\)/);
  });

  it('styles parameter controls with shared surface variables', () => {
    const css = readCss('webbed_duck/static/assets/wd/params.css');
    expect(css).toMatch(/\.param-field input,[^}]*background: var\(--wd-control-bg\)/);
    expect(css).toMatch(/\.param-field input::placeholder[^}]*var\(--wd-control-placeholder\)/);
    expect(css).toMatch(/\.param-actions button[^}]*background: var\(--wd-accent\)/);
  });

  it('exposes a resizable multi-select panel with adaptive limits', () => {
    const css = readCss('webbed_duck/static/assets/wd/multi_select.css');
    expect(css).toMatch(/\.wd-multi-select \{[^}]*--wd-multi-panel-max-height: 20rem;/);
    expect(css).toMatch(/\.wd-multi-select-panel[^}]*max-height: min\(var\(--wd-multi-panel-max-height\), 70vh\)/);
    expect(css).toMatch(/\.wd-multi-select-panel[^}]*resize: vertical/);
  });
});
