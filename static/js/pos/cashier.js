(function () {
    'use strict';

    let currentOrderId = null;
    let currentOrderTotal = 0;
    let currentPaymentId = null;
    let modifierQty = 1;
    let pendingProduct = null;

    // ── WebSocket ──────────────────────────────────────────────────────────
    const ws = new WebSocket(`ws://${location.host}/ws/pos/cashier/${STORE_ID}/`);
    ws.onmessage = function (e) {
        const msg = JSON.parse(e.data);
        if (msg.event === 'order.new') showNewOrderBanner(msg);
        if (msg.event === 'order.payment_confirmed') refreshPaymentStatus(msg);
        updateTabTitle();
    };

    function showNewOrderBanner(msg) {
        const banner = document.getElementById('pos-new-order-banner');
        document.getElementById('pos-new-order-text').textContent =
            `Pesanan baru: ${msg.order_number} (${msg.source})`;
        banner.style.display = 'flex';
        playBeep();
        setTimeout(() => banner.style.display = 'none', 8000);
    }

    function playBeep() {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        osc.connect(ctx.destination);
        osc.frequency.value = 880;
        osc.start();
        osc.stop(ctx.currentTime + 0.15);
    }

    let unreadCount = 0;
    function updateTabTitle() {
        unreadCount++;
        document.title = `(${unreadCount}) Kasir — Naveda POS`;
    }
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) { unreadCount = 0; document.title = 'Kasir — Naveda POS'; }
    });

    // ── Category Filter ────────────────────────────────────────────────────
    document.querySelectorAll('.pos-cat-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.pos-cat-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            const cat = this.dataset.cat;
            document.querySelectorAll('.pos-product-card').forEach(card => {
                card.style.display = (!cat || card.dataset.cat === cat) ? '' : 'none';
            });
        });
    });

    // ── Search ─────────────────────────────────────────────────────────────
    document.getElementById('product-search').addEventListener('input', function () {
        const q = this.value.toLowerCase();
        document.querySelectorAll('.pos-product-card').forEach(card => {
            card.style.display = card.dataset.name.toLowerCase().includes(q) ? '' : 'none';
        });
    });

    // ── Product Click → Add to Order ──────────────────────────────────────
    document.querySelectorAll('.pos-product-card').forEach(card => {
        card.addEventListener('click', async function () {
            pendingProduct = {
                id: parseInt(this.dataset.id),
                name: this.dataset.name,
                price: parseFloat(this.dataset.price),
                hasModifiers: this.dataset.hasModifiers === 'true',
            };
            if (pendingProduct.hasModifiers) {
                openModifierModal(this);
            } else {
                await ensureOrderExists();
                await addItemToOrder(pendingProduct.id, 1, [], '');
            }
        });
    });

    // ── Modifier Modal ────────────────────────────────────────────────────
    function openModifierModal(card) {
        modifierQty = 1;
        document.getElementById('modifier-product-name').textContent = card.dataset.name;
        document.getElementById('modifier-qty-display').textContent = '1';
        document.getElementById('modifier-item-notes').value = '';
        const container = document.getElementById('modifier-groups-container');
        container.innerHTML = '';
        const groups = JSON.parse(card.dataset.modifiersJson || '[]');
        groups.forEach(group => {
            const div = document.createElement('div');
            div.className = 'pos-modifier-group';
            div.innerHTML = `<h4>${group.name} ${group.is_required ? '<span class="ni-badge ni-badge-warning">Wajib</span>' : ''}</h4>`;
            group.options.forEach(opt => {
                const inputType = group.max_selections === 1 ? 'radio' : 'checkbox';
                div.innerHTML += `<label class="pos-modifier-option">
                    <input type="${inputType}" name="group_${group.id}" value="${opt.id}" data-price="${opt.additional_price}">
                    ${opt.name} ${opt.additional_price > 0 ? `+Rp ${opt.additional_price.toLocaleString()}` : ''}
                </label>`;
            });
            container.appendChild(div);
        });
        document.getElementById('modifier-modal').style.display = 'flex';
    }

    document.getElementById('close-modifier-modal').onclick = () => {
        document.getElementById('modifier-modal').style.display = 'none';
    };
    document.getElementById('modifier-qty-minus').onclick = () => {
        if (modifierQty > 1) { modifierQty--; document.getElementById('modifier-qty-display').textContent = modifierQty; }
    };
    document.getElementById('modifier-qty-plus').onclick = () => {
        modifierQty++; document.getElementById('modifier-qty-display').textContent = modifierQty;
    };
    document.getElementById('confirm-add-item-btn').addEventListener('click', async () => {
        const selectedIds = [...document.querySelectorAll('#modifier-groups-container input:checked')].map(i => parseInt(i.value));
        const notes = document.getElementById('modifier-item-notes').value;
        await ensureOrderExists();
        await addItemToOrder(pendingProduct.id, modifierQty, selectedIds, notes);
        document.getElementById('modifier-modal').style.display = 'none';
    });

    // ── Core Order Functions ──────────────────────────────────────────────
    async function ensureOrderExists() {
        if (currentOrderId) return;
        const res = await fetch('/pos/api/orders/create/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
            body: JSON.stringify({
                store_id: STORE_ID,
                order_type: document.getElementById('order-type').value,
                table_number: document.getElementById('order-table').value,
                customer_name: document.getElementById('order-customer').value,
            }),
        });
        const data = await res.json();
        currentOrderId = data.order_id;
        document.getElementById('pay-btn').disabled = false;
    }

    async function addItemToOrder(productId, qty, modifierIds, notes) {
        const res = await fetch(`/pos/api/orders/${currentOrderId}/add-item/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
            body: JSON.stringify({product_id: productId, quantity: qty, modifier_option_ids: modifierIds, notes}),
        });
        const data = await res.json();
        if (data.errors) { alert(data.errors.join('\n')); return; }
        currentOrderTotal = parseFloat(data.order_total);
        refreshOrderDisplay();
    }

    function refreshOrderDisplay() {
        fetch(`/pos/orders/${currentOrderId}/`).then(r => r.text()).then(() => {
            // Update totals display from server response
        });
    }

    // ── Payment Modal ─────────────────────────────────────────────────────
    document.getElementById('pay-btn').addEventListener('click', async () => {
        if (!currentOrderId) return;
        await fetch(`/pos/api/orders/${currentOrderId}/submit/`, {
            method: 'POST', headers: {'X-CSRFToken': CSRF},
        });
        document.getElementById('modal-total').textContent = `Rp ${currentOrderTotal.toLocaleString()}`;
        renderPaymentMethods();
        document.getElementById('payment-modal').style.display = 'flex';
    });

    document.getElementById('close-payment-modal').onclick = () => {
        document.getElementById('payment-modal').style.display = 'none';
    };

    function renderPaymentMethods() {
        const container = document.getElementById('payment-method-buttons');
        container.innerHTML = '';
        PAYMENT_METHODS.forEach(method => {
            const btn = document.createElement('button');
            btn.className = 'ni-btn ni-btn-secondary pos-method-btn';
            btn.textContent = method.name;
            btn.onclick = () => selectPaymentMethod(method);
            container.appendChild(btn);
        });
    }

    let selectedMethod = null;
    function selectPaymentMethod(method) {
        document.getElementById('cash-change-section').style.display = method.type === 'CASH' ? 'block' : 'none';
        document.getElementById('qris-section').style.display = method.type === 'QRIS' ? 'block' : 'none';
        document.getElementById('transfer-section').style.display = method.type === 'TRANSFER' ? 'block' : 'none';
        if (method.type === 'QRIS' && method.qris) {
            document.getElementById('qris-image').src = method.qris;
        }
        if (method.type === 'CASH') {
            addPaymentRow(method, currentOrderTotal, '', true);
        }
        selectedMethod = method;
    }

    async function addPaymentRow(method, amount, ref, autoConfirm) {
        const res = await fetch(`/pos/api/orders/${currentOrderId}/pay/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
            body: JSON.stringify({payment_method_id: method.id, amount, reference_number: ref}),
        });
        const data = await res.json();
        currentPaymentId = data.payment_id;
        if (data.is_fully_paid) enableCompleteButton();
    }

    document.getElementById('cash-received').addEventListener('input', function () {
        const change = parseFloat(this.value || 0) - currentOrderTotal;
        document.getElementById('cash-change').textContent = `Rp ${Math.max(0, change).toLocaleString()}`;
    });

    document.getElementById('confirm-qris-btn').addEventListener('click', async () => {
        if (!currentPaymentId) await addPaymentRow(selectedMethod, currentOrderTotal, '', false);
        await fetch(`/pos/api/payments/${currentPaymentId}/confirm/`, {method: 'POST', headers: {'X-CSRFToken': CSRF}});
        document.getElementById('confirm-qris-btn').textContent = '✓ Dikonfirmasi';
        document.getElementById('confirm-qris-btn').disabled = true;
        enableCompleteButton();
    });

    document.getElementById('confirm-transfer-btn').addEventListener('click', async () => {
        const ref = document.getElementById('transfer-ref').value;
        if (!currentPaymentId) await addPaymentRow(selectedMethod, currentOrderTotal, ref, false);
        await fetch(`/pos/api/payments/${currentPaymentId}/confirm/`, {method: 'POST', headers: {'X-CSRFToken': CSRF}});
        enableCompleteButton();
    });

    function enableCompleteButton() {
        document.getElementById('complete-order-btn').disabled = false;
    }

    document.getElementById('complete-order-btn').addEventListener('click', async () => {
        const res = await fetch(`/pos/api/orders/${currentOrderId}/complete/`, {
            method: 'POST', headers: {'X-CSRFToken': CSRF},
        });
        const data = await res.json();
        if (data.status === 'COMPLETED') {
            document.getElementById('payment-modal').style.display = 'none';
            currentOrderId = null;
            currentOrderTotal = 0;
            document.getElementById('order-items').innerHTML = '<p class="pos-order-empty">Pilih produk untuk mulai pesanan</p>';
            document.getElementById('pay-btn').disabled = true;
            document.querySelectorAll('#display-subtotal, #display-tax, #display-service, #display-total').forEach(el => el.textContent = 'Rp 0');
        }
    });
})();
