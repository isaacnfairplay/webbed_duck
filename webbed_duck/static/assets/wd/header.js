function initHeader(header) {
  if (!header || header.dataset.wdHeaderInit) {
    return;
  }
  header.dataset.wdHeaderInit = '1';
  const root = document.documentElement;
  const filters = header.querySelector('[data-wd-filters]');
  const toggleTop = header.querySelector('[data-wd-top-toggle]');
  const toggleFilters = header.querySelector('[data-wd-filters-toggle]');
  const themeToggle = header.querySelector('[data-wd-theme-toggle]');
  let lastScrollY = window.scrollY || 0;
  let measuredHeight = header.getBoundingClientRect().height;
  let ticking = false;

  function setOffset(forceMeasure = false, override) {
    if (forceMeasure) {
      measuredHeight = header.getBoundingClientRect().height;
    }
    const value = override !== undefined ? override : measuredHeight;
    root.style.setProperty('--wd-top-offset', `${value}px`);
  }

  function showHeader() {
    header.setAttribute('data-hidden', 'false');
    setOffset(true);
  }

  function hideHeader() {
    header.setAttribute('data-hidden', 'true');
    setOffset(false, 0);
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

  if (themeToggle) {
    const storageKey = 'wd-theme';
    const storage = (() => {
      try {
        return window.localStorage || null;
      } catch (error) {
        console.warn('Local storage is not available for theme persistence.', error); // eslint-disable-line no-console
        return null;
      }
    })();
    let hasStoredPreference = false;
    let currentTheme = 'light';
    const prefersDark =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-color-scheme: dark)')
        : null;
    let systemTheme = prefersDark && prefersDark.matches ? 'dark' : 'light';

    const getLabel = (name, fallback) => themeToggle.dataset[name] || fallback;

    const applyTheme = (theme, { persist } = { persist: true }) => {
      if (theme === 'system') {
        currentTheme = systemTheme;
        delete root.dataset.wdTheme;
        if (storage && (persist || hasStoredPreference)) {
          try {
            storage.removeItem(storageKey);
          } catch (error) {
            console.warn('Unable to clear stored theme', error); // eslint-disable-line no-console
          }
        }
        hasStoredPreference = false;
        updateThemeButton();
        return;
      }

      currentTheme = theme === 'dark' ? 'dark' : 'light';
      root.dataset.wdTheme = currentTheme;
      if (persist && storage) {
        try {
          storage.setItem(storageKey, currentTheme);
          hasStoredPreference = true;
        } catch (error) {
          console.warn('Unable to persist theme', error); // eslint-disable-line no-console
        }
      }
      updateThemeButton();
    };

    const updateThemeButton = () => {
      const darkLabel = getLabel('darkLabel', 'Use dark theme');
      const lightLabel = getLabel('lightLabel', 'Use light theme');
      const systemLabel = getLabel('systemLabel', 'System theme ({theme})');

      if (!hasStoredPreference) {
        const descriptor = systemTheme === 'dark' ? 'dark' : 'light';
        themeToggle.textContent = systemLabel.replace('{theme}', descriptor);
        themeToggle.setAttribute('aria-pressed', 'mixed');
        themeToggle.dataset.mode = 'system';
        return;
      }

      const isDark = currentTheme === 'dark';
      themeToggle.textContent = isDark ? lightLabel : darkLabel;
      themeToggle.setAttribute('aria-pressed', isDark ? 'true' : 'false');
      themeToggle.dataset.mode = currentTheme;
    };

    if (storage) {
      try {
        const storedTheme = storage.getItem(storageKey);
        if (storedTheme === 'dark' || storedTheme === 'light') {
          hasStoredPreference = true;
          applyTheme(storedTheme, { persist: false });
        } else {
          hasStoredPreference = false;
          applyTheme('system', { persist: false });
        }
      } catch (error) {
        console.warn('Unable to read stored theme preference', error); // eslint-disable-line no-console
        hasStoredPreference = false;
        applyTheme('system', { persist: false });
      }
    } else {
      hasStoredPreference = false;
      applyTheme('system', { persist: false });
    }

    if (prefersDark) {
      const updateSystemTheme = (event) => {
        systemTheme = event.matches ? 'dark' : 'light';
        if (!hasStoredPreference) {
          applyTheme('system', { persist: false });
        } else {
          updateThemeButton();
        }
      };
      if (typeof prefersDark.addEventListener === 'function') {
        prefersDark.addEventListener('change', updateSystemTheme);
      } else if (typeof prefersDark.addListener === 'function') {
        prefersDark.addListener(updateSystemTheme);
      }
    }

    themeToggle.title =
      themeToggle.dataset.hint ||
      'Click to toggle theme. Alt-click to follow your system preference.';

    themeToggle.addEventListener('click', (event) => {
      if (event.altKey) {
        applyTheme('system', { persist: true });
        return;
      }
      if (!hasStoredPreference) {
        const desired = systemTheme === 'dark' ? 'light' : 'dark';
        applyTheme(desired, { persist: true });
        return;
      }
      const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
      applyTheme(nextTheme, { persist: true });
    });
  }

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
