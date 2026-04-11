/**
 * Naveda Integra — sidebar.js
 * Sidebar navigation: collapse/expand, mobile toggle, submenu toggle
 */
(function () {
  'use strict';

  /* Lucide icons --------------------------------------------------------- */
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  /* DOM refs -------------------------------------------------------------- */
  var sidebar = document.getElementById('sidebar');
  var sidebarToggle = document.getElementById('sidebarToggle');
  var mobileToggle = document.getElementById('mobileToggle');
  var overlay = document.getElementById('sidebarOverlay');

  if (!sidebar) return; /* Not logged-in page */

  /* Collapse / Expand (desktop) ------------------------------------------ */
  var COLLAPSED_KEY = 'ni_sidebar_collapsed';

  function applySidebarState() {
    if (localStorage.getItem(COLLAPSED_KEY) === '1') {
      sidebar.classList.add('ni-sidebar--collapsed');
    }
  }
  applySidebarState();

  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('ni-sidebar--collapsed');
      localStorage.setItem(
        COLLAPSED_KEY,
        sidebar.classList.contains('ni-sidebar--collapsed') ? '1' : '0'
      );
    });
  }

  /* Mobile open / close -------------------------------------------------- */
  function openMobile() {
    sidebar.classList.add('ni-sidebar--open');
    if (overlay) overlay.classList.add('ni-sidebar-overlay--visible');
    document.body.style.overflow = 'hidden';
  }

  function closeMobile() {
    sidebar.classList.remove('ni-sidebar--open');
    if (overlay) overlay.classList.remove('ni-sidebar-overlay--visible');
    document.body.style.overflow = '';
  }

  if (mobileToggle) mobileToggle.addEventListener('click', openMobile);
  if (overlay) overlay.addEventListener('click', closeMobile);

  /* Submenu toggle ------------------------------------------------------- */
  var submenuToggles = document.querySelectorAll('[data-toggle="submenu"]');
  submenuToggles.forEach(function (el) {
    el.addEventListener('click', function () {
      var parent = el.closest('.ni-nav-item');
      if (parent) parent.classList.toggle('ni-nav-item--open');
    });
  });
})();
