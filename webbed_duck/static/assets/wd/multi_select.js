function initMultiSelect(container) {
  if (!container || container.dataset.wdMultiInit) {
    return;
  }
  container.dataset.wdMultiInit = '1';
  const select = container.querySelector('select.wd-multi-select-input');
  if (!select) {
    return;
  }
  const toggle = container.querySelector('.wd-multi-select-toggle');
  const panel = container.querySelector('.wd-multi-select-panel');
  const search = container.querySelector('.wd-multi-select-search input');
  const summary = container.querySelector('.wd-multi-select-summary');
  const clear = container.querySelector('.wd-multi-select-clear');
  const options = Array.from(container.querySelectorAll('.wd-multi-select-option'));

  function adjustPanelHeight() {
    if (!panel) {
      return;
    }
    const visibleOptions = options.filter((li) => li.style.display !== 'none');
    const visibleCount = visibleOptions.length || options.length || 1;
    const rows = Math.min(Math.max(visibleCount, 4), 12);
    const optionHeight = 32;
    const chrome = 140; // search, padding, and actions controls
    const desired = chrome + rows * optionHeight;
    const viewportLimit = Math.max(220, Math.floor((window.innerHeight || 720) * 0.75));
    const computed = Math.min(Math.max(desired, 220), viewportLimit);
    container.style.setProperty('--wd-multi-panel-max-height', `${computed}px`);
  }

  function updateFlags() {
    options.forEach((li) => {
      const cb = li.querySelector('input');
      li.dataset.selected = cb && cb.checked ? '1' : '';
    });
  }

  function updateSummary() {
    const labels = Array.from(select.selectedOptions)
      .map((option) => (option.textContent || '').trim())
      .filter(Boolean);
    const placeholder = select.dataset.placeholder || 'All values';
    summary.textContent = labels.length ? labels.join(', ') : placeholder;
  }

  options.forEach((li) => {
    const cb = li.querySelector('input');
    if (!cb) {
      return;
    }
    cb.addEventListener('change', () => {
      Array.from(select.options).forEach((option) => {
        if (option.value === cb.value) {
          option.selected = cb.checked;
        }
      });
      updateFlags();
      updateSummary();
      adjustPanelHeight();
    });
  });

  if (clear) {
    clear.addEventListener('click', () => {
      Array.from(select.options).forEach((option) => {
        option.selected = false;
      });
      options.forEach((li) => {
        const cb = li.querySelector('input');
        if (cb) {
          cb.checked = false;
        }
      });
      updateFlags();
      updateSummary();
      adjustPanelHeight();
    });
  }

  function closePanel() {
    if (panel) {
      panel.hidden = true;
    }
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'false');
    }
  }

  if (toggle) {
    toggle.addEventListener('click', (event) => {
      event.preventDefault();
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      if (expanded) {
        closePanel();
      } else {
        toggle.setAttribute('aria-expanded', 'true');
        if (panel) {
          panel.hidden = false;
        }
        if (search) {
          setTimeout(() => {
            try {
              search.focus({ preventScroll: true });
            } catch (err) {
              search.focus();
            }
          }, 10);
        }
        adjustPanelHeight();
      }
    });
  }

  document.addEventListener('click', (event) => {
    if (!container.contains(event.target)) {
      closePanel();
    }
  });

  if (panel) {
    panel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closePanel();
        if (toggle) {
          toggle.focus();
        }
      }
    });
  }

  if (search) {
    search.addEventListener('input', () => {
      const term = search.value.toLowerCase();
      options.forEach((li) => {
        const haystack = li.getAttribute('data-search') || '';
        if (!term || li.dataset.selected === '1') {
          li.style.display = '';
        } else {
          li.style.display = haystack.indexOf(term) === -1 ? 'none' : '';
        }
      });
      adjustPanelHeight();
    });
  }

  updateFlags();
  updateSummary();
  adjustPanelHeight();

  window.addEventListener('resize', () => {
    adjustPanelHeight();
  });
}

function bootMultiSelect() {
  document.querySelectorAll('[data-wd-widget="multi"]').forEach((el) => {
    initMultiSelect(el);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootMultiSelect);
} else {
  bootMultiSelect();
}

export { initMultiSelect };
