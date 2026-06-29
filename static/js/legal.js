/* Language toggle for the legal pages. Indonesian is the default and the
   governing version. Choice is remembered per browser. */
(function () {
  'use strict';

  var STORAGE_KEY = 'naveda-legal-lang';
  var body = document.body;
  var buttons = document.querySelectorAll('[data-lang-btn]');

  function apply(lang) {
    if (lang !== 'id' && lang !== 'en') {
      lang = 'id';
    }
    body.setAttribute('data-lang', lang);
    document.documentElement.setAttribute('lang', lang);
    buttons.forEach(function (btn) {
      var active = btn.getAttribute('data-lang-btn') === lang;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) {
      /* storage unavailable — ignore */
    }
  }

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      apply(btn.getAttribute('data-lang-btn'));
    });
  });

  var saved;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch (e) {
    saved = null;
  }
  apply(saved || body.getAttribute('data-lang') || 'id');
})();
