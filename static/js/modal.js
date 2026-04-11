/**
 * Naveda Integra — modal.js
 * Lightweight modal open/close logic using data attributes.
 * Usage: <button data-modal-open="myModal">Open</button>
 *        <div class="ni-modal" id="myModal"> ... </div>
 */
(function () {
  'use strict';

  /* Open ----------------------------------------------------------------- */
  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-modal-open]');
    if (opener) {
      var modal = document.getElementById(opener.getAttribute('data-modal-open'));
      if (modal) openModal(modal);
    }

    var closer = e.target.closest('[data-modal-close]');
    if (closer) {
      var modal = closer.closest('.ni-modal');
      if (modal) closeModal(modal);
    }

    /* Close on backdrop click */
    if (e.target.classList.contains('ni-modal') && e.target.classList.contains('ni-modal--open')) {
      closeModal(e.target);
    }
  });

  /* Escape key ----------------------------------------------------------- */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var open = document.querySelector('.ni-modal--open');
      if (open) closeModal(open);
    }
  });

  function openModal(el) {
    el.classList.add('ni-modal--open');
    document.body.style.overflow = 'hidden';
  }

  function closeModal(el) {
    el.classList.remove('ni-modal--open');
    document.body.style.overflow = '';
  }

  /* Public API */
  window.niModal = { open: openModal, close: closeModal };
})();
