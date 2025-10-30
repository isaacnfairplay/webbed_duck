function loadChartJs(src) {
  if (window.Chart || !src) {
    return Promise.resolve();
  }
  if (document.querySelector(`script[data-wd-chart-src="${src}"]`)) {
    return new Promise((resolve) => {
      if (window.Chart) {
        resolve();
      } else {
        document.addEventListener('wd:chart-ready', resolve, { once: true });
      }
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.crossOrigin = 'anonymous';
    script.dataset.wdChartSrc = src;
    script.onload = () => {
      document.dispatchEvent(new CustomEvent('wd:chart-ready'));
      resolve();
    };
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function initCanvas(canvas) {
  if (!canvas || canvas.dataset.wdChartLoaded) {
    return;
  }
  const configId = canvas.getAttribute('data-wd-chart');
  if (!configId) {
    return;
  }
  const configEl = document.getElementById(configId);
  if (!configEl) {
    return;
  }
  try {
    const cfg = JSON.parse(configEl.textContent || '{}');
    const ctx = canvas.getContext('2d');
    if (ctx && window.Chart) {
      canvas.dataset.wdChartLoaded = '1';
      new window.Chart(ctx, cfg);
    }
  } catch (error) {
    console.error('Failed to boot chart', error); // eslint-disable-line no-console
  }
}

function initCharts() {
  document.querySelectorAll('canvas[data-wd-chart]').forEach(initCanvas);
}

function bootCharts() {
  const src = document.body ? document.body.dataset.wdChartSrc : '';
  loadChartJs(src).then(initCharts).catch((error) => {
    console.error('Failed to load Chart.js', error); // eslint-disable-line no-console
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootCharts);
} else {
  bootCharts();
}

export { initCharts, initCanvas, loadChartJs };
