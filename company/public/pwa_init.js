if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/assets/company/service-worker.js')
      .then(reg => console.log('✅ Service Worker registered', reg))
      .catch(err => console.warn('❌ Service Worker failed', err));
  });
}

// Dynamically inject manifest
const link = document.createElement('link');
link.rel = 'manifest';
link.href = '/assets/company/manifest.json';
document.head.appendChild(link);
