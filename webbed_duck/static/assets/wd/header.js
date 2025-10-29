function initHeader(header) {
  if (!header || header.dataset.wdHeaderInit) {
    return;
  }
  header.dataset.wdHeaderInit = '1';
  const root = document.documentElement;
  const filters = header.querySelector('[data-wd-filters]');
  const toggleTop = header.querySelector('[data-wd-top-toggle]');
  const toggleFilters = header.querySelector('[data-wd-filters-toggle]');
  let lastScrollY = window.scrollY || 0;
  let measuredHeight = header.getBoundingClientRect().height;
  let ticking = false;

  function setOffset(forceMeasure = false) {
    if (forceMeasure) {
      measuredHeight = header.getBoundingClientRect().height;
    }
    root.style.setProperty('--wd-top-offset', `${measuredHeight}px`);
  }

  function showHeader() {
    header.setAttribute('data-hidden', 'false');
    setOffset();
  }

  function hideHeader() {
    header.setAttribute('data-hidden', 'true');
  }

  function updateTopButton() {
    if (!toggleTop) {
      return;
    }
    const collapsed = header.getAttribute('data-collapsed') === 'true';
    const hideLabel = toggleTop.dataset.hideLabel || 'Hide header';
    const showLabel = toggleTop.dataset.showLabel || 'Show header';
    toggleTop.textContent = collapsed ? showLabel : hideLabel;
    toggleTop.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  }

  function updateFiltersButton() {
    if (!toggleFilters) {
      return;
    }
    if (!filters) {
      toggleFilters.style.display = 'none';
      return;
    }
    const hidden = filters.hasAttribute('hidden');
    const hideLabel = toggleFilters.dataset.hideLabel || 'Hide filters';
    const showLabel = toggleFilters.dataset.showLabel || 'Show filters';
    toggleFilters.textContent = hidden ? showLabel : hideLabel;
    toggleFilters.setAttribute('aria-expanded', hidden ? 'false' : 'true');
  }

  if (toggleTop) {
    toggleTop.addEventListener('click', () => {
      const collapsed = header.getAttribute('data-collapsed') === 'true';
      header.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
      header.setAttribute('data-hidden', 'false');
      updateTopButton();
      requestAnimationFrame(() => setOffset(true));
    });
    updateTopButton();
  }

  if (toggleFilters && filters) {
    toggleFilters.addEventListener('click', () => {
      if (filters.hasAttribute('hidden')) {
        filters.removeAttribute('hidden');
      } else {
        filters.setAttribute('hidden', '');
      }
      updateFiltersButton();
      requestAnimationFrame(() => setOffset(true));
    });
    updateFiltersButton();
  }

  function handleScroll() {
    const current = window.scrollY || 0;
    const delta = current - lastScrollY;
    lastScrollY = current;
    const collapsed = header.getAttribute('data-collapsed') === 'true';
    if (collapsed) {
      showHeader();
      return;
    }
    if (delta > 12 && current > 24) {
      hideHeader();
    } else if (delta < -12) {
      showHeader();
    }
  }

  window.addEventListener('scroll', () => {
    if (!ticking) {
      window.requestAnimationFrame(() => {
        handleScroll();
        ticking = false;
      });
      ticking = true;
    }
  });

  window.addEventListener('resize', () => {
    window.requestAnimationFrame(() => setOffset(true));
  });

  header.addEventListener('mouseenter', showHeader);
  header.addEventListener('focusin', showHeader);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Home') {
      showHeader();
    }
  });

  setOffset(true);
}

function bootHeader() {
  const header = document.querySelector('[data-wd-top]');
  if (header) {
    initHeader(header);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootHeader);
} else {
  bootHeader();
}

export { initHeader };
