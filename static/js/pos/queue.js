(function () {
    'use strict';

    const ws = new WebSocket(`ws://${location.host}/ws/pos/kitchen/${STORE_ID}/`);
    ws.onmessage = function (e) {
        const msg = JSON.parse(e.data);
        handleOrderEvent(msg);
    };

    function handleOrderEvent(msg) {
        if (msg.event === 'order.new') {
            fetchAndInsertCard(msg.order_number, 'col-pending');
        } else if (msg.event === 'order.status') {
            moveCard(msg.order_number, msg.status);
        } else if (msg.event === 'order.cancelled') {
            const card = document.getElementById(`card-${msg.order_number}`);
            if (card) card.remove();
        }
        updateCounts();
    }

    function moveCard(orderNumber, newStatus) {
        const card = document.getElementById(`card-${orderNumber}`);
        if (!card) return;
        const colMap = {
            'OPEN': 'col-pending',
            'IN_QUEUE': 'col-preparing',
            'PREPARING': 'col-preparing',
            'READY': 'col-ready',
        };
        const col = document.getElementById(colMap[newStatus]);
        if (col) { col.appendChild(card); updateCounts(); }
        if (newStatus === 'COMPLETED' || newStatus === 'CANCELLED') card.remove();
    }

    async function fetchAndInsertCard(orderNumber, colId) {
        const col = document.getElementById(colId);
        const div = document.createElement('div');
        div.className = 'pos-order-card pos-card-new';
        div.id = `card-${orderNumber}`;
        div.innerHTML = `<strong>${orderNumber}</strong> <small>Baru masuk</small>`;
        col.prepend(div);
    }

    function updateCounts() {
        ['pending', 'preparing', 'ready'].forEach(key => {
            const colId = `col-${key}`;
            const countId = `count-${key}`;
            const count = document.getElementById(colId)?.children.length || 0;
            const el = document.getElementById(countId);
            if (el) el.textContent = count;
        });
    }

    document.addEventListener('click', async function (e) {
        const btn = e.target.closest('.pos-advance-btn');
        if (!btn) return;
        const orderPk = btn.dataset.orderPk;
        const nextStatus = btn.dataset.nextStatus;
        await fetch(`/pos/api/orders/${orderPk}/transition/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
            body: JSON.stringify({status: nextStatus}),
        });
    });
})();
