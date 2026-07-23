/**
 * Aggregator onboarding wizard.
 *
 * Every state-changing action is a normal POST form, so the wizard works with
 * JavaScript disabled and every action is CSRF-protected and audited server
 * side. This file only adds two things on top:
 *
 *   1. Confirmation before destructive or outward-facing actions.
 *   2. The outlet picker, which fetches outlets discovered on the merchant's
 *      aggregator account and fills a branch row when one is chosen.
 *
 * Handlers are attached here by data attribute — never inline in the template.
 */
(function () {
  'use strict';

  function onReady(fn) {
    if (document.readyState !== 'loading') {
      fn();
    } else {
      document.addEventListener('DOMContentLoaded', fn);
    }
  }

  /** Confirm before submitting any form carrying data-agg-confirm. */
  function wireConfirmations() {
    document.querySelectorAll('form[data-agg-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (!window.confirm(form.getAttribute('data-agg-confirm'))) {
          event.preventDefault();
        }
      });
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /**
   * Render the outlets returned by the server.
   *
   * Address is shown as prominently as name on purpose: branch names are often
   * near-identical, and picking the wrong outlet sends one branch's orders to
   * another branch's kitchen.
   */
  function renderOutlets(container, outlets) {
    container.innerHTML = '';
    container.hidden = false;

    if (!outlets.length) {
      container.appendChild(
        el('p', 'ni-text-muted ni-text-sm',
           'Tidak ada outlet ditemukan. Pastikan outlet sudah terdaftar di portal aggregator ' +
           'dan akun yang Anda setujui memilikinya.')
      );
      return;
    }

    container.appendChild(
      el('p', 'ni-text-muted ni-text-sm',
         'Klik outlet untuk mengisi Store ID pada baris cabang yang cocok. ' +
         'Cocokkan berdasarkan alamat.')
    );

    var list = el('div', 'ni-agg-outlet-grid');
    outlets.forEach(function (outlet) {
      var card = el('button', 'ni-agg-outlet');
      card.type = 'button';
      card.appendChild(el('span', 'ni-agg-outlet__name', outlet.name || '(tanpa nama)'));
      card.appendChild(el('span', 'ni-agg-outlet__address', outlet.address || 'Alamat tidak tersedia'));
      card.appendChild(el('span', 'ni-agg-outlet__id', outlet.external_id));

      card.addEventListener('click', function () {
        selectOutlet(outlet, card);
      });
      list.appendChild(card);
    });
    container.appendChild(list);
  }

  var pendingOutlet = null;

  /** Arm an outlet, then let the operator click the branch input to apply it. */
  function selectOutlet(outlet, card) {
    pendingOutlet = outlet;
    document.querySelectorAll('.ni-agg-outlet--active').forEach(function (node) {
      node.classList.remove('ni-agg-outlet--active');
    });
    card.classList.add('ni-agg-outlet--active');

    document.querySelectorAll('[data-agg-store-input]').forEach(function (input) {
      input.classList.add('ni-input--awaiting');
    });
  }

  function wireBranchInputs() {
    document.querySelectorAll('[data-agg-store-input]').forEach(function (input) {
      input.addEventListener('focus', function () {
        if (!pendingOutlet) return;
        var storePk = input.getAttribute('data-agg-store-input');
        input.value = pendingOutlet.external_id;

        var nameField = document.querySelector('[data-agg-store-name="' + storePk + '"]');
        var addressField = document.querySelector('[data-agg-store-address="' + storePk + '"]');
        if (nameField) nameField.value = pendingOutlet.name || '';
        if (addressField) addressField.value = pendingOutlet.address || '';

        pendingOutlet = null;
        document.querySelectorAll('.ni-agg-outlet--active').forEach(function (node) {
          node.classList.remove('ni-agg-outlet--active');
        });
        document.querySelectorAll('.ni-input--awaiting').forEach(function (node) {
          node.classList.remove('ni-input--awaiting');
        });
      });
    });
  }

  function wireOutletLoader() {
    var button = document.querySelector('[data-agg-load-outlets]');
    var container = document.querySelector('[data-agg-outlet-list]');
    if (!button || !container) return;

    button.addEventListener('click', function () {
      button.disabled = true;
      var original = button.textContent;
      button.textContent = 'Memuat…';

      fetch(button.getAttribute('data-url'), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.ok) {
            renderOutlets(container, data.outlets || []);
          } else {
            container.hidden = false;
            container.innerHTML = '';
            container.appendChild(
              el('div', 'ni-alert ni-alert--danger', data.error || 'Gagal memuat outlet.')
            );
          }
        })
        .catch(function () {
          container.hidden = false;
          container.innerHTML = '';
          container.appendChild(
            el('div', 'ni-alert ni-alert--danger',
               'Tidak bisa menghubungi server. Periksa koneksi lalu coba lagi.')
          );
        })
        .finally(function () {
          button.disabled = false;
          button.textContent = original;
        });
    });
  }

  onReady(function () {
    wireConfirmations();
    wireOutletLoader();
    wireBranchInputs();
  });
})();
