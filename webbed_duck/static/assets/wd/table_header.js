function initTableHeader(container) {
  if (!container || container.dataset.wdTableInit) {
    return;
  }
  const scroller = container.querySelector('.wd-table-scroller');
  const table = container.querySelector('table');
  const mini = container.querySelector('[data-wd-table-mini]');
  const thead = table ? table.querySelector('thead') : null;
  if (!scroller || !mini || !thead) {
    return;
  }

  container.dataset.wdTableInit = '1';

  const headerCells = Array.from(thead.querySelectorAll('th'));
  if (headerCells.length) {
    mini.innerHTML = '';
    headerCells.forEach((cell) => {
      const span = document.createElement('span');
      span.className = 'wd-table-mini-label';
      span.textContent = (cell.textContent || '').trim();
      mini.appendChild(span);
    });
  }

  mini.hidden = true;

  const showMini = (visible) => {
    mini.hidden = !visible;
  };

  const handleEntry = (entry) => {
    if (!entry) {
      return;
    }
    const headerVisible = entry.isIntersecting && entry.intersectionRatio > 0;
    showMini(!headerVisible);
  };

  if (typeof window !== 'undefined' && 'IntersectionObserver' in window) {
    const observer = new window.IntersectionObserver(
      (entries) => {
        handleEntry(entries && entries[0]);
      },
      {
        root: scroller,
        threshold: [0, 1],
      },
    );
    observer.observe(thead);
    container.addEventListener(
      'wd:destroy',
      () => {
        observer.disconnect();
      },
      { once: true },
    );
  } else {
    const fallback = () => {
      const headerRect = thead.getBoundingClientRect();
      const scrollerRect = scroller.getBoundingClientRect();
      const visible =
        headerRect.bottom > scrollerRect.top && headerRect.top < scrollerRect.bottom;
      showMini(!visible);
    };
    scroller.addEventListener('scroll', fallback, { passive: true });
    window.addEventListener('resize', fallback);
    container.addEventListener(
      'wd:destroy',
      () => {
        scroller.removeEventListener('scroll', fallback);
        window.removeEventListener('resize', fallback);
      },
      { once: true },
    );
    fallback();
  }
}

function bootTableHeaders() {
  document.querySelectorAll('[data-wd-table]').forEach((el) => {
    initTableHeader(el);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootTableHeaders);
} else {
  bootTableHeaders();
}

export { initTableHeader };
