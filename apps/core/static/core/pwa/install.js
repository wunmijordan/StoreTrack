(() => {
  const root = document.getElementById('pwa-install-root');
  if (!root) return;

  const scope = root.dataset.pwaScope || 'brand';
  const prefix = `inprofic:pwa-install:${scope}`;
  const hiddenKey = `${prefix}:hidden`;
  const snoozeKey = `${prefix}:snooze`;
  const shownKey = `${prefix}:shown`;
  const installModal = document.getElementById('pwa-install-modal');
  const iosModal = document.getElementById('pwa-ios-install-modal');
  const installButton = document.getElementById('pwa-install-button');
  let deferredPrompt = null;

  const storage = {
    get(store, key) { try { return store.getItem(key); } catch (_) { return null; } },
    set(store, key, value) { try { store.setItem(key, value); } catch (_) {} },
  };

  function isInstalled() {
    return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  }

  function shouldShow() {
    if (isInstalled()) return false;
    if (storage.get(localStorage, hiddenKey) === 'true') return false;
    const snooze = Number(storage.get(localStorage, snoozeKey) || 0);
    if (snooze && Date.now() < snooze) return false;
    if (storage.get(sessionStorage, shownKey) === 'true') return false;
    return true;
  }

  function snooze(days = 7) {
    storage.set(localStorage, snoozeKey, String(Date.now() + days * 86400000));
  }

  function show(modal) {
    if (!modal || !shouldShow()) return;
    storage.set(sessionStorage, shownKey, 'true');
    modal.hidden = false;
    requestAnimationFrame(() => modal.classList.add('show'));
  }

  function hide(modal) {
    if (!modal) return;
    modal.classList.remove('show');
    window.setTimeout(() => { modal.hidden = true; }, 240);
  }

  function closeModal(modal) {
    const never = modal?.querySelector('[data-pwa-never]');
    if (never?.checked) storage.set(localStorage, hiddenKey, 'true');
    else snooze();
    hide(modal);
  }

  root.querySelectorAll('[data-pwa-close]').forEach((button) => {
    button.addEventListener('click', () => closeModal(button.closest('.pwa-modal')));
  });
  root.querySelectorAll('.pwa-modal').forEach((modal) => {
    modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(modal); });
  });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).catch(() => {});
    }, { once: true });
  }

  window.addEventListener('beforeinstallprompt', (event) => {
    if (!shouldShow()) return;
    event.preventDefault();
    deferredPrompt = event;
    window.setTimeout(() => show(installModal), 900);
  });

  installButton?.addEventListener('click', async () => {
    if (!deferredPrompt) return;
    hide(installModal);
    deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    if (choice.outcome === 'accepted') storage.set(localStorage, hiddenKey, 'true');
    else snooze();
    deferredPrompt = null;
  });

  window.addEventListener('appinstalled', () => {
    storage.set(localStorage, hiddenKey, 'true');
    hide(installModal);
    hide(iosModal);
  });

  document.addEventListener('DOMContentLoaded', () => {
    const ua = navigator.userAgent || '';
    const iOS = /iphone|ipad|ipod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    if (iOS && shouldShow()) window.setTimeout(() => show(iosModal), 1200);
  });
})();
