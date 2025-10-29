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
    });
  }

  updateFlags();
  updateSummary();
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
