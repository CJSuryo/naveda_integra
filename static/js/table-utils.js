/**
 * Naveda Integra — table-utils.js
 * Lightweight table utilities: row-click navigation, empty state.
 */
(function () {
  'use strict';

  /* Clickable rows – add data-href="..." to <tr> to make entire row clickable */
  document.addEventListener('click', function (e) {
    if (e.target.closest('a, button, input, .ni-btn')) return;
    var row = e.target.closest('tr[data-href]');
    if (row) {
      window.location.href = row.getAttribute('data-href');
    }
  });
})();
