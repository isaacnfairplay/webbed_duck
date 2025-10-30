import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { initCanvas, initCharts, loadChartJs } from '../webbed_duck/static/assets/wd/chart_boot.js';

describe('chart boot helpers', () => {
  let originalChart: typeof window.Chart;

  beforeEach(() => {
    originalChart = window.Chart;
    // Ensure a clean DOM for each test
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    delete document.body.dataset.wdChartSrc;
  });

  afterEach(() => {
    window.Chart = originalChart;
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    delete document.body.dataset.wdChartSrc;
  });

  it('loads Chart.js once and resolves after the script fires load', async () => {
    const appendSpy = vi.spyOn(document.head, 'appendChild').mockImplementation((node: Node) => {
      if (node instanceof HTMLScriptElement) {
        // Simulate a successful load after the script is appended
        if (typeof node.onload === 'function') {
          node.onload(new Event('load') as unknown as Event);
        }
      }
      return node;
    });
    const readySpy = vi.fn();
    document.addEventListener('wd:chart-ready', readySpy, { once: true });

    await loadChartJs('https://cdn.example.com/chart.js');
    expect(appendSpy).toHaveBeenCalledTimes(1);
    expect(readySpy).toHaveBeenCalledTimes(1);

    window.Chart = {} as typeof window.Chart;

    appendSpy.mockClear();
    await loadChartJs('https://cdn.example.com/chart.js');
    expect(appendSpy).not.toHaveBeenCalled();
    appendSpy.mockRestore();
  });

  it('initializes canvases when a configuration element exists', () => {
    const canvas = document.createElement('canvas');
    canvas.dataset.wdChart = 'cfg-1';
    const contextSpy = vi.fn().mockReturnValue({});
    // @ts-expect-error - override for testing
    canvas.getContext = contextSpy;

    const config = { type: 'bar', data: { labels: ['a'], datasets: [] } };
    const configEl = document.createElement('script');
    configEl.id = 'cfg-1';
    configEl.type = 'application/json';
    configEl.textContent = JSON.stringify(config);

    window.Chart = vi.fn();

    document.body.append(canvas, configEl);
    initCanvas(canvas);

    expect(canvas.dataset.wdChartLoaded).toBe('1');
    expect(contextSpy).toHaveBeenCalledWith('2d');
    expect(window.Chart).toHaveBeenCalledTimes(1);
    expect(window.Chart).toHaveBeenCalledWith(contextSpy.mock.results[0].value, config);
  });

  it('skips canvases without matching configuration', () => {
    const canvas = document.createElement('canvas');
    canvas.dataset.wdChart = 'missing';
    const contextSpy = vi.fn();
    // @ts-expect-error - override for testing
    canvas.getContext = contextSpy;

    window.Chart = vi.fn();

    document.body.append(canvas);
    initCanvas(canvas);

    expect(canvas.dataset.wdChartLoaded).toBeUndefined();
    expect(window.Chart).not.toHaveBeenCalled();
  });

  it('boots all canvases via initCharts', () => {
    window.Chart = vi.fn();

    const makeCanvas = (id: string) => {
      const canvas = document.createElement('canvas');
      canvas.dataset.wdChart = id;
      // @ts-expect-error - override for testing
      canvas.getContext = vi.fn().mockReturnValue({});
      const configEl = document.createElement('script');
      configEl.id = id;
      configEl.type = 'application/json';
      configEl.textContent = JSON.stringify({ type: 'line', data: {} });
      document.body.append(canvas, configEl);
    };

    makeCanvas('cfg-1');
    makeCanvas('cfg-2');

    initCharts();
    expect(window.Chart).toHaveBeenCalledTimes(2);
  });
});
