const PROGRESS_SELECTOR = '[data-wd-progress]';
const BAR_SELECTOR = '[data-wd-progress-bar]';
const FORM_SELECTOR = 'form[data-wd-widget="params"]';

function initProgress(root) {
  if (!root) {
    return;
  }
  if (root.dataset.wdProgressInit) {
    return;
  }
  const bar = root.querySelector(BAR_SELECTOR);
  if (!bar) {
    return;
  }
  root.dataset.wdProgressInit = '1';

  let active = false;
  let timeouts = [];
  let hideTimeout = null;

  const clearTimers = () => {
    timeouts.forEach((id) => window.clearTimeout(id));
    timeouts = [];
    if (hideTimeout !== null) {
      window.clearTimeout(hideTimeout);
      hideTimeout = null;
    }
  };

  const setActiveState = (value) => {
    if (value) {
      root.hidden = false;
      root.setAttribute('aria-hidden', 'false');
      root.dataset.active = 'true';
      return;
    }
    root.dataset.active = 'false';
    root.setAttribute('aria-hidden', 'true');
    root.hidden = true;
  };

  const scheduleWidth = (width, delay, duration) => {
    const id = window.setTimeout(() => {
      if (!active) {
        return;
      }
      bar.style.transition = `width ${duration}ms ease`;
      bar.style.width = `${width}%`;
    }, delay);
    timeouts.push(id);
  };

  const start = () => {
    if (active) {
      return;
    }
    clearTimers();
    active = true;
    setActiveState(true);
    bar.style.transition = 'none';
    bar.style.width = '0%';
    // Force style recalculation before applying transitions.
    void bar.offsetWidth; // eslint-disable-line no-unused-expressions
    bar.style.transition = 'width 250ms ease';
    bar.style.width = '22%';
    scheduleWidth(55, 300, 900);
    scheduleWidth(80, 1100, 1300);
  };

  const finish = () => {
    if (!active) {
      setActiveState(false);
      return;
    }
    clearTimers();
    bar.style.transition = 'width 200ms ease';
    bar.style.width = '100%';
    active = false;
    hideTimeout = window.setTimeout(() => {
      bar.style.transition = 'none';
      bar.style.width = '0%';
      setActiveState(false);
    }, 240);
  };

  if (document.readyState !== 'complete') {
    start();
    window.addEventListener(
      'load',
      () => {
        finish();
      },
      { once: true },
    );
  } else {
    finish();
  }

  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      finish();
    }
  });

  document.addEventListener(
    'submit',
    (event) => {
      const target = event.target;
      if (!(target instanceof HTMLFormElement)) {
        return;
      }
      if (!target.matches(FORM_SELECTOR)) {
        return;
      }
      start();
    },
    true,
  );
}

function bootProgress() {
  const root = document.querySelector(PROGRESS_SELECTOR);
  if (!root) {
    return;
  }
  initProgress(root);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootProgress);
} else {
  bootProgress();
}

export { initProgress };
