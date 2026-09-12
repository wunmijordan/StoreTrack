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
  const updateLaterKey = 'inprofic:pwa-update:later-this-session';
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

  const updateModal = document.getElementById('pwa-update-modal');
  const updateButton = document.getElementById('pwa-update-button');
  const updateLater = document.getElementById('pwa-update-later');
  let waitingWorker = null;
  let updateReloadArmed = false;

  function showUpdate(worker) {
    if (!worker || !navigator.serviceWorker.controller || !updateModal) return;
    if (storage.get(sessionStorage, updateLaterKey) === 'true') return;
    waitingWorker = worker;
    updateModal.hidden = false;
    requestAnimationFrame(() => updateModal.classList.add('show'));
  }
  function hideUpdate() { hide(updateModal); }
  function deferUpdate() { storage.set(sessionStorage, updateLaterKey, 'true'); hideUpdate(); }
  updateLater?.addEventListener('click', deferUpdate);
  root.querySelectorAll('[data-pwa-update-later]').forEach(button => button.addEventListener('click', deferUpdate));
  updateButton?.addEventListener('click', () => {
    if (!waitingWorker) return;
    updateReloadArmed = true;
    updateButton.disabled = true;
    updateButton.textContent = 'Updating…';
    waitingWorker.postMessage({ type: 'SKIP_WAITING' });
  });

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!updateReloadArmed) return;
      updateReloadArmed = false;
      window.location.reload();
    });
    window.addEventListener('load', async () => {
      try {
        const registration = await navigator.serviceWorker.register('/service-worker.js', { scope: '/', updateViaCache: 'none' });
        if (registration.waiting && navigator.serviceWorker.controller) showUpdate(registration.waiting);
        registration.addEventListener('updatefound', () => {
          const worker = registration.installing;
          if (!worker) return;
          worker.addEventListener('statechange', () => {
            if (worker.state === 'installed' && navigator.serviceWorker.controller) showUpdate(worker);
          });
        });
        // Render deployments embed their git commit into the service-worker body.
        // Ask the browser to compare now rather than waiting for its periodic check.
        window.setTimeout(() => registration.update().catch(() => {}), 2500);
      } catch (_) {}
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
