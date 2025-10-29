function initParamsForm(form) {
  if (!form || form.dataset.wdParamsInit) {
    return;
  }
  form.dataset.wdParamsInit = '1';
  // Placeholder for future enhancements (validation, persistence, etc.)
}

function bootParamsForms() {
  document.querySelectorAll('[data-wd-widget="params"]').forEach((form) => {
    initParamsForm(form);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootParamsForms);
} else {
  bootParamsForms();
}

export { initParamsForm };
