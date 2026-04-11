/**
 * Naveda Integra — toast.js
 * Auto-dismiss toast notifications and close button handling
 */
(function () {
  'use strict';

  var DISMISS_DELAY = 5000; /* ms */

  /* Close button --------------------------------------------------------- */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-dismiss="toast"]');
    if (!btn) return;
    var toast = btn.closest('.ni-toast');
    if (toast) dismissToast(toast);
  });

  /* Auto-dismiss --------------------------------------------------------- */
  var toasts = document.querySelectorAll('.ni-toast');
  toasts.forEach(function (toast) {
    setTimeout(function () { dismissToast(toast); }, DISMISS_DELAY);
  });

  function dismissToast(el) {
    el.style.opacity = '0';
    el.style.transform = 'translateY(-8px)';
    setTimeout(function () { el.remove(); }, 250);
  }
})();
