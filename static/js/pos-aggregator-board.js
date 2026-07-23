/**
 * Live order board.
 *
 * The socket is an enhancement, never the guarantee: every order shown here is
 * already committed server-side and also delivered by web push. If the socket
 * drops, the board falls back to reloading, so a lost connection costs a
 * refresh — never an order.
 */
(function () {
  'use strict';

  var RECONNECT_BASE_MS = 1000;
  var RECONNECT_MAX_MS = 30000;
  /** After this many failed attempts, reload rather than keep retrying blind. */
  var RELOAD_AFTER_ATTEMPTS = 8;

  function onReady(fn) {
    if (document.readyState !== 'loading') {
      fn();
    } else {
      document.addEventListener('DOMContentLoaded', fn);
    }
  }

  function setStatus(state, text) {
    var badge = document.querySelector('[data-agg-connection]');
    if (!badge) return;
    badge.textContent = text;
    badge.className = 'ni-badge ni-badge--' + state;
  }

  function notify(payload) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    try {
      new Notification('Pesanan ' + payload.aggregator_label + ' baru', {
        body: '#' + payload.order_number + ' — Rp ' + payload.total_amount,
        tag: 'agg-order-' + payload.id
      });
    } catch (err) {
      /* Notification construction can throw on some mobile browsers. */
    }
  }

  onReady(function () {
    var board = document.querySelector('[data-agg-board]');
    if (!board) return;

    var storePk = board.getAttribute('data-store-pk');
    var scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    var url = scheme + '://' + window.location.host + '/ws/pos/branch/' + storePk + '/orders/';

    var attempts = 0;
    var socket = null;

    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    function connect() {
      socket = new WebSocket(url);

      socket.addEventListener('open', function () {
        attempts = 0;
        setStatus('success', 'Terhubung');
      });

      socket.addEventListener('message', function (event) {
        var message;
        try {
          message = JSON.parse(event.data);
        } catch (err) {
          return;
        }
        if (message.type === 'order.new') {
          notify(message.payload || {});
          // Re-render server-side so the card matches the list exactly and no
          // display logic is duplicated in the browser.
          window.location.reload();
        }
      });

      socket.addEventListener('close', function () {
        attempts += 1;
        if (attempts >= RELOAD_AFTER_ATTEMPTS) {
          window.location.reload();
          return;
        }
        setStatus('warning', 'Terputus — menyambung ulang…');
        var delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, attempts), RECONNECT_MAX_MS);
        window.setTimeout(connect, delay);
      });

      socket.addEventListener('error', function () {
        setStatus('danger', 'Gangguan koneksi');
      });
    }

    connect();
  });
})();
