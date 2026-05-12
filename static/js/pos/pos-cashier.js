/**
 * POS Cashier — vanilla JS, no jQuery dependency.
 * Handles item grid, cart, modifier modal, payment modal, and form submission.
 */
(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────────────────────
  let allItems = [];    // raw items from API
  let cart = [];        // [{item_pk, name, qty, base_price, modifier_total, modifier_summary, is_bulk}]
  let sttAccounts = {   // filled by api/stt-defaults
    offset_account_id: '',
    revenue_account_id: '',
    payment_account_id: '',
    inventory_account_id: '',
    tax_account_id: '',
    tax_type: '',
  };
  let pendingItem = null; // item waiting for modifier selection
  let selectedStoreLv3 = '';
  let selectedSttId = '';
  let paymentMethod = 'tunai'; // 'tunai' | 'nontunai'

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const storeSelect   = document.getElementById('posStoreSelect');
  const sttSelect     = document.getElementById('posSttSelect');
  const searchInput   = document.getElementById('posSearch');
  const itemGrid      = document.getElementById('posItemGrid');
  const cartBody      = document.getElementById('posCartBody');
  const cartCount     = document.getElementById('posCartCount');
  const totalDisplay  = document.getElementById('posTotalDisplay');
  const bayarBtn      = document.getElementById('posBayarBtn');
  const submitForm    = document.getElementById('posSubmitForm');
  const formEbGroups  = document.getElementById('formEbGroupsData');

  // Modifier modal
  const modOverlay    = document.getElementById('modifierModalOverlay');
  const modTitle      = document.getElementById('modifierModalTitle');
  const modBody       = document.getElementById('modifierModalBody');
  const modClose      = document.getElementById('modifierModalClose');
  const modCancel     = document.getElementById('modifierModalCancel');
  const modConfirm    = document.getElementById('modifierModalConfirm');

  // Payment modal
  const payOverlay    = document.getElementById('paymentModalOverlay');
  const payTotal      = document.getElementById('payTotalDisplay');
  const payClose      = document.getElementById('paymentModalClose');
  const payCancel     = document.getElementById('paymentModalCancel');
  const payConfirm    = document.getElementById('paymentConfirmBtn');
  const cashInput     = document.getElementById('cashReceived');
  const changeDisplay = document.getElementById('changeDisplay');
  const tabBtns       = document.querySelectorAll('.ni-pos-tab-btn');

  // ── Helpers ────────────────────────────────────────────────────────────────
  function fmtRp(n) {
    return 'Rp ' + Math.floor(n).toLocaleString('id-ID');
  }

  function cartTotal() {
    return cart.reduce(function (sum, row) {
      return sum + (row.base_price + row.modifier_total) * row.qty;
    }, 0);
  }

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  // ── Item grid ──────────────────────────────────────────────────────────────
  function renderGrid(filter) {
    filter = (filter || '').toLowerCase();
    var filtered = allItems.filter(function (it) {
      if (!filter) return true;
      return (it.name || '').toLowerCase().includes(filter) ||
             (it.kode_item || '').toLowerCase().includes(filter);
    });

    if (filtered.length === 0) {
      itemGrid.innerHTML = '<div class="ni-pos-empty" style="grid-column:1/-1">' +
        (allItems.length === 0 ? 'Tidak ada item untuk toko ini.' : 'Item tidak ditemukan.') +
        '</div>';
      return;
    }

    var html = '';
    filtered.forEach(function (it) {
      html += '<div class="ni-pos-item-card" data-item-pk="' + it.item_pk + '">' +
        '<div class="ni-pos-item-card__name">' + escHtml(it.name) + '</div>' +
        '<div class="ni-pos-item-card__code">' + escHtml(it.kode_item) + '</div>' +
        '<div class="ni-pos-item-card__price">' + fmtRp(parseFloat(it.selling_price) || 0) + '</div>' +
        '</div>';
    });
    itemGrid.innerHTML = html;

    // Attach click handlers
    itemGrid.querySelectorAll('.ni-pos-item-card').forEach(function (card) {
      card.addEventListener('click', function () {
        var pk = parseInt(card.getAttribute('data-item-pk'));
        var item = allItems.find(function (i) { return i.item_pk === pk; });
        if (item) onItemClick(item);
      });
    });
  }

  function escHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Load items from API ────────────────────────────────────────────────────
  function loadItems(lv3Pk) {
    itemGrid.innerHTML = '<div class="ni-pos-empty" style="grid-column:1/-1">Memuat item...</div>';
    allItems = [];
    fetch('/sales/api/pos-items/?lv3_pk=' + encodeURIComponent(lv3Pk), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        allItems = data.items || [];
        renderGrid(searchInput.value);
      })
      .catch(function () {
        itemGrid.innerHTML = '<div class="ni-pos-empty" style="grid-column:1/-1">Gagal memuat item.</div>';
      });
  }

  // ── STT defaults ──────────────────────────────────────────────────────────
  function loadSttDefaults(sttId) {
    if (!sttId) {
      sttAccounts = { offset_account_id: '', revenue_account_id: '', payment_account_id: '', inventory_account_id: '', tax_account_id: '', tax_type: '' };
      return;
    }
    fetch('/sales/api/stt-defaults/?stt_id=' + encodeURIComponent(sttId), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.ok) {
          sttAccounts.offset_account_id    = data.offset_account_id    || '';
          sttAccounts.revenue_account_id   = data.revenue_account_id   || '';
          sttAccounts.payment_account_id   = data.payment_account_id   || '';
          sttAccounts.inventory_account_id = data.inventory_account_id || '';
          sttAccounts.tax_account_id       = data.tax_account_id       || '';
          sttAccounts.tax_type             = data.tax_type             || '';
        }
      })
      .catch(function () {});
  }

  // ── Item click → maybe show modifier modal ─────────────────────────────────
  function onItemClick(item) {
    if (item.modifier_groups && item.modifier_groups.length > 0) {
      pendingItem = item;
      openModifierModal(item);
    } else {
      addToCart(item, [], 0, '');
    }
  }

  // ── Modifier modal ─────────────────────────────────────────────────────────
  function openModifierModal(item) {
    modTitle.textContent = item.name;
    var html = '';
    (item.modifier_groups || []).forEach(function (grp) {
      var isMulti = grp.max_selections > 1;
      html += '<div class="ni-pos-modifier-group" data-grp-pk="' + grp.pk + '" data-required="' + (grp.is_required ? '1' : '0') + '" data-min="' + grp.min_selections + '" data-max="' + grp.max_selections + '">' +
        '<div class="ni-pos-modifier-group__label">' + escHtml(grp.nama) +
        (grp.is_required ? '<span class="ni-pos-modifier-group__required">*wajib</span>' : '') +
        '</div>';
      (grp.options || []).forEach(function (opt) {
        var inputType = isMulti ? 'checkbox' : 'radio';
        var inputName = 'mod_grp_' + grp.pk;
        html += '<label class="ni-pos-modifier-option">' +
          '<input type="' + inputType + '" name="' + inputName + '" value="' + opt.pk + '" data-price="' + opt.additional_price + '" data-name="' + escHtml(opt.name) + '"' +
          (opt.is_default ? ' checked' : '') + '>' +
          '<span>' + escHtml(opt.name) + '</span>' +
          (parseFloat(opt.additional_price) > 0 ? '<span class="ni-pos-modifier-option__price">+' + fmtRp(parseFloat(opt.additional_price)) + '</span>' : '') +
          '</label>';
      });
      html += '</div>';
    });
    modBody.innerHTML = html;
    modOverlay.classList.remove('ni-hidden');
  }

  function closeModifierModal() {
    modOverlay.classList.add('ni-hidden');
    modBody.innerHTML = '';
    pendingItem = null;
  }

  function confirmModifiers() {
    if (!pendingItem) { closeModifierModal(); return; }

    // Validate and collect selections
    var groups = modBody.querySelectorAll('.ni-pos-modifier-group');
    var valid = true;
    var modifierTotal = 0;
    var summaryParts = [];

    groups.forEach(function (grpEl) {
      var min = parseInt(grpEl.getAttribute('data-min')) || 0;
      var max = parseInt(grpEl.getAttribute('data-max')) || 1;
      var inputs = grpEl.querySelectorAll('input:checked');
      var count = inputs.length;
      if (count < min) {
        valid = false;
        var label = grpEl.querySelector('.ni-pos-modifier-group__label');
        if (label) label.style.color = 'var(--ni-danger, #e53e3e)';
      } else {
        var label = grpEl.querySelector('.ni-pos-modifier-group__label');
        if (label) label.style.color = '';
      }
      if (count > max) {
        valid = false;
      }
      inputs.forEach(function (inp) {
        modifierTotal += parseFloat(inp.getAttribute('data-price')) || 0;
        summaryParts.push(inp.getAttribute('data-name'));
      });
    });

    if (!valid) return;

    var summary = summaryParts.join(', ');
    addToCart(pendingItem, [], modifierTotal, summary);
    closeModifierModal();
  }

  modClose.addEventListener('click', closeModifierModal);
  modCancel.addEventListener('click', closeModifierModal);
  modConfirm.addEventListener('click', confirmModifiers);
  modOverlay.addEventListener('click', function (e) {
    if (e.target === modOverlay) closeModifierModal();
  });

  // ── Cart operations ────────────────────────────────────────────────────────
  function addToCart(item, _opts, modifierTotal, modifierSummary) {
    // For non-bulk items, group by item_pk + modifierSummary
    if (!item.is_bulk) {
      var existing = cart.find(function (r) {
        return r.item_pk === item.item_pk && r.modifier_summary === modifierSummary;
      });
      if (existing) {
        existing.qty += 1;
        renderCart();
        return;
      }
    }
    cart.push({
      item_pk: item.item_pk,
      name: item.name,
      qty: 1,
      base_price: parseFloat(item.selling_price) || 0,
      modifier_total: modifierTotal || 0,
      modifier_summary: modifierSummary || '',
      is_bulk: item.is_bulk || false,
    });
    renderCart();
  }

  function removeFromCart(idx) {
    cart.splice(idx, 1);
    renderCart();
  }

  function changeQty(idx, delta) {
    cart[idx].qty = Math.max(1, cart[idx].qty + delta);
    renderCart();
  }

  function renderCart() {
    if (cart.length === 0) {
      cartBody.innerHTML = '<div class="ni-pos-cart-empty">Belum ada item.</div>';
      cartCount.textContent = '0 item';
      totalDisplay.textContent = 'Rp 0';
      bayarBtn.disabled = true;
      return;
    }

    var total = cartTotal();
    var html = '';
    cart.forEach(function (row, idx) {
      var rowTotal = (row.base_price + row.modifier_total) * row.qty;
      html += '<div class="ni-pos-cart-item">' +
        '<div class="ni-pos-cart-item__top">' +
        '<div class="ni-pos-cart-item__name">' + escHtml(row.name) + '</div>' +
        '<button class="ni-pos-cart-item__del" data-idx="' + idx + '" aria-label="Hapus">&times;</button>' +
        '</div>';
      if (row.modifier_summary) {
        html += '<div class="ni-pos-cart-item__modifier">' + escHtml(row.modifier_summary) + '</div>';
      }
      html += '<div class="ni-pos-cart-item__bottom">' +
        '<div class="ni-pos-qty-controls">' +
        '<button class="ni-pos-qty-btn" data-idx="' + idx + '" data-delta="-1">−</button>' +
        '<span class="ni-pos-qty-val">' + row.qty + '</span>' +
        '<button class="ni-pos-qty-btn" data-idx="' + idx + '" data-delta="1">+</button>' +
        '</div>' +
        '<span class="ni-pos-cart-item__subtotal">' + fmtRp(rowTotal) + '</span>' +
        '</div></div>';
    });
    cartBody.innerHTML = html;

    // Event delegation
    cartBody.querySelectorAll('.ni-pos-cart-item__del').forEach(function (btn) {
      btn.addEventListener('click', function () { removeFromCart(parseInt(btn.getAttribute('data-idx'))); });
    });
    cartBody.querySelectorAll('.ni-pos-qty-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        changeQty(parseInt(btn.getAttribute('data-idx')), parseInt(btn.getAttribute('data-delta')));
      });
    });

    var itemCount = cart.reduce(function (s, r) { return s + r.qty; }, 0);
    cartCount.textContent = itemCount + ' item';
    totalDisplay.textContent = fmtRp(total);
    bayarBtn.disabled = (cart.length === 0 || !selectedStoreLv3 || !selectedSttId);
  }

  // ── Payment modal ──────────────────────────────────────────────────────────
  function openPaymentModal() {
    var total = cartTotal();
    payTotal.textContent = fmtRp(total);
    cashInput.value = '';
    changeDisplay.textContent = 'Rp 0';
    changeDisplay.classList.remove('negative');
    payOverlay.classList.remove('ni-hidden');
  }

  function closePaymentModal() {
    payOverlay.classList.add('ni-hidden');
  }

  function updateChange() {
    var total = cartTotal();
    var received = parseFloat(cashInput.value) || 0;
    var change = received - total;
    changeDisplay.textContent = fmtRp(Math.abs(change));
    if (change < 0) {
      changeDisplay.classList.add('negative');
    } else {
      changeDisplay.classList.remove('negative');
    }
  }

  cashInput.addEventListener('input', updateChange);

  tabBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      paymentMethod = btn.getAttribute('data-tab');
      tabBtns.forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      document.getElementById('tabTunai').classList.toggle('active', paymentMethod === 'tunai');
      document.getElementById('tabNontunai').classList.toggle('active', paymentMethod === 'nontunai');
    });
  });

  bayarBtn.addEventListener('click', openPaymentModal);
  payClose.addEventListener('click', closePaymentModal);
  payCancel.addEventListener('click', closePaymentModal);
  payOverlay.addEventListener('click', function (e) { if (e.target === payOverlay) closePaymentModal(); });

  payConfirm.addEventListener('click', function () {
    if (paymentMethod === 'tunai') {
      var total = cartTotal();
      var received = parseFloat(cashInput.value) || 0;
      if (received < total) {
        cashInput.style.borderColor = 'var(--ni-danger, #e53e3e)';
        return;
      }
      cashInput.style.borderColor = '';
    }
    closePaymentModal();
    submitSale();
  });

  // ── Build eb_groups_data and submit ───────────────────────────────────────
  function submitSale() {
    if (!selectedStoreLv3 || !selectedSttId || cart.length === 0) return;

    var items = cart.map(function (row) {
      return {
        item_id: row.item_pk,
        sub_transaction_type_id: parseInt(selectedSttId),
        quantity: row.is_bulk ? '0.0000' : row.qty.toFixed(4),
        selling_price: (row.base_price + row.modifier_total).toFixed(4),
        offset_coa_account_id: sttAccounts.offset_account_id,
        revenue_account_id: sttAccounts.revenue_account_id,
        payment_account_id: sttAccounts.payment_account_id,
        is_bulk: row.is_bulk ? '1' : '0',
      };
    });

    var ebGroupsData = [{
      eb_selection: 'lv3:' + selectedStoreLv3,
      items: items,
    }];

    formEbGroups.value = JSON.stringify(ebGroupsData);
    submitForm.submit();
  }

  // ── Store selection ────────────────────────────────────────────────────────
  storeSelect.addEventListener('change', function () {
    selectedStoreLv3 = storeSelect.value;
    allItems = [];
    cart = [];
    renderCart();
    if (selectedStoreLv3) {
      loadItems(selectedStoreLv3);
    } else {
      itemGrid.innerHTML = '<div class="ni-pos-empty" style="grid-column:1/-1">Pilih toko untuk menampilkan item.</div>';
    }
  });

  // ── STT selection ──────────────────────────────────────────────────────────
  sttSelect.addEventListener('change', function () {
    selectedSttId = sttSelect.value;
    loadSttDefaults(selectedSttId);
    // Re-evaluate bayar button
    bayarBtn.disabled = (cart.length === 0 || !selectedStoreLv3 || !selectedSttId);
  });

  // ── Search ────────────────────────────────────────────────────────────────
  searchInput.addEventListener('input', function () {
    renderGrid(searchInput.value);
  });

  // ── Initial render ────────────────────────────────────────────────────────
  renderCart();

})();
