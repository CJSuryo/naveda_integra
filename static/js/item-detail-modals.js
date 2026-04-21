/**
 * item-detail-modals.js
 *
 * Reusable modal system for selecting akun → entering item detail records
 * (persediaan, aset tetap, aset lainnya, modal disetor).
 *
 * Usage:
 *   1. Include templates/components/item_detail_modals.html on the page.
 *   2. Load this script after TomSelect and Lucide.
 *   3. Call niDetailModals.init({ ... }) with page-specific config.
 *   4. In each journal row's akun onChange handler, call niDetailModals.onAkunChange(rid, kode, nama).
 *   5. On row removal, call niDetailModals.clearRow(rid).
 *   6. On form submit, read niDetailModals.getRowDetailMap() to get detail_rows per rid.
 *
 * All modal functions are also exposed as window.sa* globals for backward-compat
 * with existing onclick="" attributes in templates.
 */
(function () {
  'use strict';

  // ── Config (set via init) ─────────────────────────────────────────────────
  var cfg = {};
  var AKUN_DETAIL_MAP = {};

  // ── Shared state ─────────────────────────────────────────────────────────
  var _rowDetailMap = {};  // rid → { type, detail_rows[] }
  var _rowAkunInfo = {};   // rid → { type, kode, nama }

  // ── Persediaan modal state ────────────────────────────────────────────────
  var _modalCurrentRid = null;
  var _modalRowCount = 0;
  var _modalTomSelects = [];
  var _modalCoaTomSelect = null;

  // ── Aset Tetap modal state ────────────────────────────────────────────────
  var _atActiveRid = null;
  var _atRowCount = 0;
  var _atTomSelects = [];

  // ── Aset Lainnya modal state ──────────────────────────────────────────────
  var _alActiveRid = null;
  var _alRowCount = 0;
  var _alTomSelects = [];

  // ── Modal Disetor modal state ─────────────────────────────────────────────
  var _mdActiveRid = null;
  var _mdRowCount = 0;

  // ── Item master create modal state ────────────────────────────────────────
  var _itemCreateCallback = null;
  var _modalCoaMainTomSelect = null;
  var _modalCoaAtpTomSelect = null;
  var _modalCoaAllTomSelect = null;

  // ── Helpers ───────────────────────────────────────────────────────────────
  function formatNum(n) {
    return parseFloat(n || 0).toLocaleString('id-ID', { minimumFractionDigits: 0 });
  }

  function _getEBLv1Id() { return cfg.getEBLv1Id ? cfg.getEBLv1Id() : ''; }
  function _getEBDisplayText() { return cfg.getEBDisplayText ? cfg.getEBDisplayText() : ''; }
  function _getCsrf() { return cfg.csrfToken || ''; }

  function _getDetailTypeForAkun(kode) {
    for (var prefix in AKUN_DETAIL_MAP) {
      if (kode === prefix || kode.indexOf(prefix + '.') === 0) {
        return AKUN_DETAIL_MAP[prefix];
      }
    }
    return null;
  }

  function _updateDetailBadge(rid) {
    var badgeEl = document.getElementById('detail_badge_' + rid);
    if (!badgeEl) return;
    var d = _rowDetailMap[rid];
    if (d && d.detail_rows && d.detail_rows.length) {
      var n = d.detail_rows.length;
      var total = d.detail_rows.reduce(function (s, r) { return s + (r.total || r.jumlah || 0); }, 0);
      badgeEl.textContent = n + ' item — Rp ' + formatNum(total);
    } else {
      badgeEl.textContent = '';
    }
  }

  function _onAkunChange(rid, kode, akunNama) {
    var detailType = _getDetailTypeForAkun(kode);
    var wrapEl = document.getElementById('detail_wrap_' + rid);
    if (!wrapEl) return;

    if (detailType) {
      wrapEl.style.display = '';
      _rowAkunInfo[rid] = { type: detailType, kode: kode, nama: akunNama };

      // Clear stale detail if type changed
      if (_rowDetailMap[rid] && _rowDetailMap[rid].type !== detailType) {
        _rowDetailMap[rid] = null;
        _updateDetailBadge(rid);
        if (cfg.onDetailCleared) cfg.onDetailCleared(rid);
      }

      var btn = wrapEl.querySelector('button');
      if (btn) {
        var icon, title, opener;
        if (detailType === 'persediaan') {
          icon = 'package'; title = 'Isi detail persediaan';
          opener = (function (r) { return function () { openPersediaanModal(r); }; })(rid);
        } else if (detailType === 'aset_tetap') {
          icon = 'landmark'; title = 'Isi detail aset tetap';
          opener = (function (r) { return function () { openAsetTetapModal(r); }; })(rid);
        } else if (detailType === 'aset_lainnya') {
          icon = 'database'; title = 'Isi detail aset lainnya';
          opener = (function (r) { return function () { openAsetLainnyaModal(r); }; })(rid);
        } else if (detailType === 'modal_disetor') {
          icon = 'wallet'; title = 'Isi rincian modal disetor';
          opener = (function (r) { return function () { openModalDisetorModal(r); }; })(rid);
        }
        if (opener) {
          btn.title = title;
          btn.innerHTML = '<i data-lucide="' + icon + '" style="width:13px;height:13px"></i>';
          btn.onclick = opener;
          lucide.createIcons();
        }
      }
    } else {
      wrapEl.style.display = 'none';
      _rowDetailMap[rid] = null;
      _rowAkunInfo[rid] = null;
      _updateDetailBadge(rid);
      if (cfg.onDetailCleared) cfg.onDetailCleared(rid);
    }
  }

  // ── Persediaan modal ──────────────────────────────────────────────────────
  function openPersediaanModal(rid) {
    _modalCurrentRid = rid;
    var info = _rowAkunInfo[rid] || {};
    document.getElementById('saModalAkunNama').textContent = info.nama || '';
    _clearModalRows();
    var existing = _rowDetailMap[rid];
    if (existing && existing.detail_rows && existing.detail_rows.length) {
      existing.detail_rows.forEach(function (d) { modalAddRow(d); });
    } else {
      modalAddRow();
    }
    document.getElementById('saModalPersediaanBackdrop').classList.add('ni-modal-backdrop--visible');
  }

  function closePersediaanModal() {
    document.getElementById('saModalPersediaanBackdrop').classList.remove('ni-modal-backdrop--visible');
  }

  function _clearModalRows() {
    _modalTomSelects.forEach(function (ts) { try { ts.destroy(); } catch (e) {} });
    _modalTomSelects = [];
    document.getElementById('saModalRows').innerHTML = '';
    _modalRowCount = 0;
    _updatePersediaanTotal();
  }

  function modalAddRow(prefill) {
    _modalRowCount++;
    var mrid = _modalRowCount;
    var tbody = document.getElementById('saModalRows');
    var tr = document.createElement('tr');
    tr.id = 'modal_row_' + mrid;
    tr.innerHTML =
      '<td><select id="modal_item_' + mrid + '" placeholder="Ketik item…"></select></td>' +
      '<td><input type="number" id="modal_qty_' + mrid + '" class="ni-jm-input" min="0.0001" step="0.0001" value="0" oninput="saModalUpdateRow(' + mrid + ')"></td>' +
      '<td><input type="number" id="modal_unit_price_' + mrid + '" class="ni-jm-input" min="0" step="1" value="0" oninput="saModalUpdateRow(' + mrid + ')"></td>' +
      '<td><input type="number" id="modal_total_' + mrid + '" class="ni-jm-input" readonly style="background:var(--ni-bg);" value="0"></td>' +
      '<td><button type="button" class="ni-btn ni-btn--outline-danger ni-btn--sm" onclick="saModalRemoveRow(' + mrid + ')" style="padding:4px 8px;"><i data-lucide="trash-2" style="width:12px;height:12px"></i></button></td>';
    tbody.appendChild(tr);

    var currentMrid = mrid;
    var ebLv1 = _getEBLv1Id();
    var ts = new TomSelect('#modal_item_' + mrid, {
      valueField: 'id',
      labelField: 'text',
      searchField: 'text',
      options: [],
      maxOptions: false,
      placeholder: 'Ketik kode/nama item…',
      preload: 'focus',
      shouldLoad: function () { return false; },
      load: function (query, callback) {
        var url = cfg.itemAutocompleteUrl + '?term=' + encodeURIComponent(query);
        if (ebLv1) url += '&eb_lv1_id=' + encodeURIComponent(ebLv1);
        fetch(url)
          .then(function (r) { return r.json(); })
          .then(function (data) { callback(data); })
          .catch(function () { callback(); });
      },
      onChange: function () { saModalUpdateRow(currentMrid); },
      create: function (input, callback) {
        openItemModal(input, function (newOpt) {
          var selEl = document.getElementById('modal_item_' + currentMrid);
          if (selEl && selEl.tomselect) {
            selEl.tomselect.addOption(newOpt);
            selEl.tomselect.setValue(newOpt.id, true);
          }
        }, null);
        callback();
      },
      createFilter: function (input) { return input.trim().length >= 2; },
      render: {
        option_create: function (data, escape) {
          return '<div class="create">Tambah item baru: <strong>' + escape(data.input) + '</strong></div>';
        },
      },
      dropdownParent: 'body',
    });
    _modalTomSelects.push(ts);

    if (prefill) {
      if (prefill.item_id) {
        var opt = { id: String(prefill.item_id), text: prefill.item_text || String(prefill.item_id) };
        ts.addOption(opt);
        ts.setValue(String(prefill.item_id), true);
      }
      if (prefill.qty) { document.getElementById('modal_qty_' + mrid).value = prefill.qty; }
      if (prefill.unit_price) { document.getElementById('modal_unit_price_' + mrid).value = prefill.unit_price; }
      saModalUpdateRow(mrid);
    }
    lucide.createIcons();
    _updatePersediaanTotal();
  }

  function modalRemoveRow(mrid) {
    var tr = document.getElementById('modal_row_' + mrid);
    if (!tr) return;
    var sel = document.getElementById('modal_item_' + mrid);
    if (sel && sel.tomselect) {
      var idx = _modalTomSelects.indexOf(sel.tomselect);
      if (idx !== -1) _modalTomSelects.splice(idx, 1);
      sel.tomselect.destroy();
    }
    tr.remove();
    _updatePersediaanTotal();
  }

  function _updatePersediaanTotal() {
    var total = 0;
    document.querySelectorAll('#saModalRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('modal_row_', '');
      var t = parseFloat((document.getElementById('modal_total_' + mrid) || {}).value || 0);
      total += t;
    });
    var el = document.getElementById('saModalTotal');
    if (el) el.textContent = 'Rp ' + formatNum(total);
  }

  function _collectModalRows() {
    var results = [];
    document.querySelectorAll('#saModalRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('modal_row_', '');
      var selEl = document.getElementById('modal_item_' + mrid);
      var qty = parseFloat((document.getElementById('modal_qty_' + mrid) || {}).value || 0);
      var hp = parseFloat((document.getElementById('modal_unit_price_' + mrid) || {}).value || 0);
      if (!selEl || !selEl.value || qty <= 0 || hp < 0) return;
      var ts = selEl.tomselect;
      var opt = ts ? ts.options[selEl.value] : null;
      results.push({
        item_id: selEl.value,
        item_text: opt ? opt.text : String(selEl.value),
        qty: qty,
        unit_price: hp,
        total: qty * hp,
      });
    });
    return results;
  }

  function confirmPersediaanDetail() {
    var rid = _modalCurrentRid;
    if (!rid) return;
    var detailRows = _collectModalRows();
    if (!detailRows.length) {
      alert('Minimal 1 item persediaan harus diisi dengan item, qty > 0, dan harga valid.');
      return;
    }
    var grandTotal = detailRows.reduce(function (s, r) { return s + r.total; }, 0);
    _rowDetailMap[rid] = { type: 'persediaan', detail_rows: detailRows };
    if (cfg.onDebitConfirmed) cfg.onDebitConfirmed(rid, grandTotal);
    _updateDetailBadge(rid);
    closePersediaanModal();
  }

  // ── Item master create modal ──────────────────────────────────────────────
  function _initItemModalCoaTomSelects() {
    var tsConfig = {
      valueField: 'id', labelField: 'text', searchField: 'text',
      placeholder: 'Ketik kode/nama akun...', dropdownParent: 'body',
      maxOptions: false, preload: 'focus',
      shouldLoad: function () { return false; },
      load: function (q, cb) {
        fetch((cfg.autocompleteUrl || '') + '?term=' + encodeURIComponent(q) + '&all=1')
          .then(function (r) { return r.json(); }).then(cb).catch(function () { cb(); });
      },
    };
    if (!_modalCoaMainTomSelect) {
      var el1 = document.querySelector('#modal_coa_account');
      if (el1) _modalCoaMainTomSelect = new TomSelect('#modal_coa_account', Object.assign({}, tsConfig));
    }
    if (!_modalCoaAtpTomSelect) {
      var el2 = document.querySelector('#modal_coa_account_atp');
      if (el2) _modalCoaAtpTomSelect = new TomSelect('#modal_coa_account_atp', Object.assign({}, tsConfig));
    }
    if (!_modalCoaAllTomSelect) {
      var el3 = document.querySelector('#modal_coa_account_all');
      if (el3) _modalCoaAllTomSelect = new TomSelect('#modal_coa_account_all', Object.assign({}, tsConfig));
    }
  }

  function loadModalKategori(tipe, ebLv1Id) {
    var sel = document.getElementById('modal_kategori');
    if (!sel) return;
    sel.innerHTML = '<option value="">Memuat...</option>';
    sel.disabled = true;
    if (!tipe || !cfg.kategoriFilterUrl) {
      sel.innerHTML = '<option value="">— Pilih tipe item dahulu —</option>';
      sel.disabled = true;
      return;
    }
    var url = cfg.kategoriFilterUrl + '?tipe_item=' + encodeURIComponent(tipe);
    if (ebLv1Id) url += '&eb_lv1_id=' + encodeURIComponent(ebLv1Id);
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        sel.innerHTML = '<option value="">— Pilih —</option>';
        data.forEach(function (k) {
          var opt = document.createElement('option');
          opt.value = k.id; opt.textContent = k.nama;
          sel.appendChild(opt);
        });
        sel.disabled = false;
      })
      .catch(function () {
        sel.innerHTML = '<option value="">— Gagal memuat —</option>';
        sel.disabled = false;
      });
  }

  function openItemModal(prefillNama, callback, tipeHint) {
    _itemCreateCallback = callback;
    var errEl = document.getElementById('modal_error');
    if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
    var namaEl = document.getElementById('modal_nama');
    if (namaEl) namaEl.value = prefillNama || '';
    var tipeEl = document.getElementById('modal_tipe_item');
    if (tipeEl) {
      if (tipeHint === 'ATP') tipeEl.value = 'ATP';
      else if (tipeHint === 'ALL') tipeEl.value = 'ALL';
      else tipeEl.value = 'RM';
    }
    _initItemModalCoaTomSelects();
    if (_modalCoaMainTomSelect) _modalCoaMainTomSelect.clear();
    if (_modalCoaAtpTomSelect) _modalCoaAtpTomSelect.clear();
    if (_modalCoaAllTomSelect) _modalCoaAllTomSelect.clear();
    // Infer CoA from calling row's akun
    var _inferRid = (tipeHint === 'ATP') ? _atActiveRid : (tipeHint === 'ALL') ? _alActiveRid : _modalCurrentRid;
    if (_inferRid) {
      var info = _rowAkunInfo[_inferRid];
      if (info && info.kode && info.nama) {
        var akunSelId = cfg.getAkunElementId ? cfg.getAkunElementId(_inferRid) : ('akun_sel_' + _inferRid);
        var selEl = document.getElementById(akunSelId);
        var akunId = selEl ? selEl.value : '';
        if (akunId) {
          var optData = { id: akunId, text: info.kode + ' — ' + info.nama };
          if (tipeHint === 'ATP' && _modalCoaAtpTomSelect) { _modalCoaAtpTomSelect.addOption(optData); _modalCoaAtpTomSelect.setValue(akunId, true); }
          else if (tipeHint === 'ALL' && _modalCoaAllTomSelect) { _modalCoaAllTomSelect.addOption(optData); _modalCoaAllTomSelect.setValue(akunId, true); }
          else if (_modalCoaMainTomSelect) { _modalCoaMainTomSelect.addOption(optData); _modalCoaMainTomSelect.setValue(akunId, true); }
        }
      }
    }
    var fields = ['modal_velocity', 'modal_lama_kadaluarsa', 'modal_threshold', 'modal_metode_biaya',
                  'modal_masa_manfaat_atp', 'modal_metode_penyusutan', 'modal_nilai_residu_atp',
                  'modal_masa_manfaat_all', 'modal_metode_amortisasi', 'modal_nilai_residu_all'];
    fields.forEach(function (id) { var el = document.getElementById(id); if (el) el.value = ''; });
    // Show EB name
    var ebText = _getEBDisplayText();
    var ebDisplay = document.getElementById('modal_eb_display');
    if (ebDisplay) {
      ebDisplay.textContent = '';
      if (ebText && ebText !== '\u2014 Pilih Entitas \u2014') {
        var strong = document.createElement('strong');
        strong.textContent = ebText;
        ebDisplay.appendChild(strong);
      } else {
        var em = document.createElement('em');
        em.textContent = 'Entitas bisnis belum dipilih';
        ebDisplay.appendChild(em);
      }
    }
    onModalTipeItemChange();
    document.getElementById('saItemMasterModalBackdrop').classList.add('ni-modal-backdrop--visible');
    lucide.createIcons();
  }

  function closeItemModal() {
    document.getElementById('saItemMasterModalBackdrop').classList.remove('ni-modal-backdrop--visible');
    _itemCreateCallback = null;
  }

  function submitItemModal() {
    var nama = (document.getElementById('modal_nama') || {}).value || '';
    nama = nama.trim();
    if (!nama) {
      var errEl = document.getElementById('modal_error');
      if (errEl) { errEl.textContent = 'Nama item wajib diisi.'; errEl.style.display = ''; }
      return;
    }
    var tipeItem = (document.getElementById('modal_tipe_item') || {}).value || 'RM';
    var ebLv1 = _getEBLv1Id();
    var payload = {
      nama: nama,
      tipe_item: tipeItem,
      kategori_id: (document.getElementById('modal_kategori') || {}).value || null,
      entitas_bisnis_ids: ebLv1 ? [parseInt(ebLv1)] : [],
    };
    if (tipeItem === 'RM' || tipeItem === 'FG' || tipeItem === 'ITM' || tipeItem === 'RMB' || tipeItem === 'FGB' || tipeItem === 'ITMB') {
      payload.velocity_category = (document.getElementById('modal_velocity') || {}).value || '';
      payload.coa_account_id = _modalCoaMainTomSelect ? _modalCoaMainTomSelect.getValue() : null;
      payload.lama_kadaluarsa = (document.getElementById('modal_lama_kadaluarsa') || {}).value || null;
      payload.threshold_days_outstanding = (document.getElementById('modal_threshold') || {}).value || null;
      payload.metode_biaya_persediaan = (document.getElementById('modal_metode_biaya') || {}).value || '';
    } else if (tipeItem === 'ATP') {
      payload.coa_account_id = _modalCoaAtpTomSelect ? _modalCoaAtpTomSelect.getValue() : null;
      payload.masa_manfaat = (document.getElementById('modal_masa_manfaat_atp') || {}).value || null;
      payload.metode_penyusutan = (document.getElementById('modal_metode_penyusutan') || {}).value || '';
      payload.nilai_residu = parseFloat((document.getElementById('modal_nilai_residu_atp') || {}).value || 0);
    } else if (tipeItem === 'ALL') {
      payload.coa_account_id = _modalCoaAllTomSelect ? _modalCoaAllTomSelect.getValue() : null;
      payload.masa_manfaat = (document.getElementById('modal_masa_manfaat_all') || {}).value || null;
      payload.metode_amortisasi = (document.getElementById('modal_metode_amortisasi') || {}).value || '';
      payload.nilai_residu = parseFloat((document.getElementById('modal_nilai_residu_all') || {}).value || 0);
    }
    fetch(cfg.itemCreateUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
      body: JSON.stringify(payload),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.error) {
        var errEl = document.getElementById('modal_error');
        if (errEl) { errEl.textContent = data.error; errEl.style.display = ''; }
        return;
      }
      if (_itemCreateCallback) _itemCreateCallback({ id: String(data.id), text: data.text || data.nama });
      closeItemModal();
    })
    .catch(function () {
      var errEl = document.getElementById('modal_error');
      if (errEl) { errEl.textContent = 'Gagal menyimpan item. Silakan coba lagi.'; errEl.style.display = ''; }
    });
  }

  // ── Kategori modal ────────────────────────────────────────────────────────
  function openKategoriModal() {
    var namaEl = document.getElementById('kat_modal_nama');
    if (namaEl) namaEl.value = '';
    var errEl = document.getElementById('kat_modal_error');
    if (errEl) errEl.style.display = 'none';
    var tipeItem = (document.getElementById('modal_tipe_item') || {}).value || '';
    var tipeLabels = { RM: 'Raw Material', FG: 'Finished Good', ITM: 'Item Lainnya', RMB: 'Raw Material Bulk', FGB: 'Finished Good Bulk', ITMB: 'Item Lainnya Bulk', ATP: 'Aset Tetap', ALL: 'Aset Lainnya' };
    var tdEl = document.getElementById('kat_modal_tipe_display');
    if (tdEl) tdEl.value = tipeLabels[tipeItem] || tipeItem;
    var ebText = _getEBDisplayText();
    var katDisplay = document.getElementById('kat_modal_eb_display');
    if (katDisplay) {
      katDisplay.textContent = '';
      if (ebText && ebText !== '— Pilih Entitas —') {
        var strong = document.createElement('strong');
        strong.textContent = ebText;
        katDisplay.appendChild(strong);
      } else {
        var em = document.createElement('em');
        em.textContent = 'Entitas bisnis belum dipilih';
        katDisplay.appendChild(em);
      }
    }
    document.getElementById('saKategoriModalBackdrop').classList.add('ni-modal-backdrop--visible');
    lucide.createIcons();
  }

  function closeKategoriModal() {
    document.getElementById('saKategoriModalBackdrop').classList.remove('ni-modal-backdrop--visible');
  }

  function submitKategoriModal() {
    var nama = ((document.getElementById('kat_modal_nama') || {}).value || '').trim();
    if (!nama) {
      var errEl = document.getElementById('kat_modal_error');
      if (errEl) { errEl.textContent = 'Nama kategori wajib diisi.'; errEl.style.display = ''; }
      return;
    }
    var tipeItem = (document.getElementById('modal_tipe_item') || {}).value || '';
    var ebLv1 = _getEBLv1Id();
    fetch(cfg.kategoriCreateUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
      body: JSON.stringify({ nama: nama, tipe_item: tipeItem, entitas_bisnis_ids: ebLv1 ? [parseInt(ebLv1)] : [] }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.error) {
        var errEl = document.getElementById('kat_modal_error');
        if (errEl) { errEl.textContent = data.error; errEl.style.display = ''; }
        return;
      }
      var kategoriSel = document.getElementById('modal_kategori');
      if (kategoriSel) {
        var opt = document.createElement('option');
        opt.value = data.id; opt.textContent = data.nama;
        kategoriSel.appendChild(opt);
        kategoriSel.value = data.id;
      }
      closeKategoriModal();
    })
    .catch(function () {
      var errEl = document.getElementById('kat_modal_error');
      if (errEl) { errEl.textContent = 'Gagal menyimpan kategori.'; errEl.style.display = ''; }
    });
  }

  // ── Aset Tetap modal ──────────────────────────────────────────────────────
  function openAsetTetapModal(rid) {
    _atActiveRid = rid;
    var info = _rowAkunInfo[rid] || {};
    document.getElementById('saModalAsetTetapAkunNama').textContent = info.nama || '';
    _clearAsetTetapRows();
    var existing = _rowDetailMap[rid];
    if (existing && existing.detail_rows && existing.detail_rows.length) {
      existing.detail_rows.forEach(function (d) { asetTetapAddRow(d); });
    } else {
      asetTetapAddRow();
    }
    document.getElementById('saModalAsetTetapBackdrop').classList.add('ni-modal-backdrop--visible');
  }

  function closeAsetTetapModal() {
    document.getElementById('saModalAsetTetapBackdrop').classList.remove('ni-modal-backdrop--visible');
    _atActiveRid = null;
  }

  function _clearAsetTetapRows() {
    _atTomSelects.forEach(function (ts) { try { ts.destroy(); } catch (e) {} });
    _atTomSelects = [];
    document.getElementById('saModalAsetTetapRows').innerHTML = '';
    _atRowCount = 0;
    _updateAsetTetapTotal();
  }

  function asetTetapAddRow(prefill) {
    _atRowCount++;
    var mrid = _atRowCount;
    var tbody = document.getElementById('saModalAsetTetapRows');
    var tr = document.createElement('tr');
    tr.id = 'at_modal_row_' + mrid;
    tr.innerHTML =
      '<td><select id="at_modal_item_' + mrid + '" placeholder="Ketik item…"></select></td>' +
      '<td><input type="number" id="at_modal_qty_' + mrid + '" class="ni-jm-input" min="0.0001" step="0.0001" value="0" oninput="saAsetTetapUpdateRow(' + mrid + ')"></td>' +
      '<td><input type="number" id="at_modal_hpp_' + mrid + '" class="ni-jm-input" min="0" step="1" value="0" oninput="saAsetTetapUpdateRow(' + mrid + ')"></td>' +
      '<td><button type="button" class="ni-btn ni-btn--outline-danger ni-btn--sm" onclick="saModalAsetTetapRemoveRow(' + mrid + ')" style="padding:4px 8px;"><i data-lucide="trash-2" style="width:12px;height:12px"></i></button></td>';
    tbody.appendChild(tr);

    var currentMrid = mrid;
    var ebLv1 = _getEBLv1Id();
    var ts = new TomSelect('#at_modal_item_' + mrid, {
      valueField: 'id', labelField: 'text', searchField: 'text',
      options: [], maxOptions: false, placeholder: 'Ketik kode/nama item…',
      preload: 'focus', shouldLoad: function () { return false; },
      load: function (query, callback) {
        var url = cfg.itemAutocompleteUrl + '?term=' + encodeURIComponent(query);
        if (ebLv1) url += '&eb_lv1_id=' + encodeURIComponent(ebLv1);
        fetch(url).then(function (r) { return r.json(); }).then(function (data) { callback(data); }).catch(function () { callback(); });
      },
      onChange: function () { _updateAsetTetapTotal(); },
      create: function (input, callback) {
        openItemModal(input, function (newOpt) {
          var selEl = document.getElementById('at_modal_item_' + currentMrid);
          if (selEl && selEl.tomselect) { selEl.tomselect.addOption(newOpt); selEl.tomselect.setValue(newOpt.id, true); }
        }, 'ATP');
        callback();
      },
      createFilter: function (input) { return input.trim().length >= 2; },
      render: { option_create: function (data, escape) { return '<div class="create">Tambah item baru: <strong>' + escape(data.input) + '</strong></div>'; } },
      dropdownParent: 'body',
    });
    _atTomSelects.push(ts);

    if (prefill) {
      if (prefill.item_id) { var opt = { id: String(prefill.item_id), text: prefill.item_text || String(prefill.item_id) }; ts.addOption(opt); ts.setValue(String(prefill.item_id), true); }
      if (prefill.qty) document.getElementById('at_modal_qty_' + mrid).value = prefill.qty;
      if (prefill.unit_price) document.getElementById('at_modal_hpp_' + mrid).value = prefill.unit_price;
      _updateAsetTetapTotal();
    }
    lucide.createIcons();
    _updateAsetTetapTotal();
  }

  function asetTetapRemoveRow(mrid) {
    var tr = document.getElementById('at_modal_row_' + mrid);
    if (!tr) return;
    var sel = document.getElementById('at_modal_item_' + mrid);
    if (sel && sel.tomselect) {
      var idx = _atTomSelects.indexOf(sel.tomselect);
      if (idx !== -1) _atTomSelects.splice(idx, 1);
      sel.tomselect.destroy();
    }
    tr.remove();
    _updateAsetTetapTotal();
  }

  function _updateAsetTetapTotal() {
    var total = 0;
    document.querySelectorAll('#saModalAsetTetapRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('at_modal_row_', '');
      var qty = parseFloat((document.getElementById('at_modal_qty_' + mrid) || {}).value || 0);
      var hpp = parseFloat((document.getElementById('at_modal_hpp_' + mrid) || {}).value || 0);
      total += qty * hpp;
    });
    var el = document.getElementById('saModalAsetTetapTotal');
    if (el) el.textContent = 'Rp ' + formatNum(total);
  }

  function _collectAsetTetapRows() {
    var results = [];
    document.querySelectorAll('#saModalAsetTetapRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('at_modal_row_', '');
      var selEl = document.getElementById('at_modal_item_' + mrid);
      var qty = parseFloat((document.getElementById('at_modal_qty_' + mrid) || {}).value || 0);
      var hpp = parseFloat((document.getElementById('at_modal_hpp_' + mrid) || {}).value || 0);
      if (!selEl || !selEl.value || qty <= 0 || hpp < 0) return;
      var ts = selEl.tomselect;
      var opt = ts ? ts.options[selEl.value] : null;
      results.push({ item_id: selEl.value, item_text: opt ? opt.text : String(selEl.value), qty: qty, unit_price: hpp, total: qty * hpp });
    });
    return results;
  }

  function confirmAsetTetapDetail() {
    var rid = _atActiveRid;
    if (!rid) return;
    var detailRows = _collectAsetTetapRows();
    if (!detailRows.length) { alert('Minimal 1 aset tetap harus diisi dengan item, qty > 0, dan nilai perolehan valid.'); return; }
    var grandTotal = detailRows.reduce(function (s, r) { return s + r.total; }, 0);
    _rowDetailMap[rid] = { type: 'aset_tetap', detail_rows: detailRows };
    if (cfg.onDebitConfirmed) cfg.onDebitConfirmed(rid, grandTotal);
    _updateDetailBadge(rid);
    closeAsetTetapModal();
  }

  // ── Aset Lainnya modal ────────────────────────────────────────────────────
  function openAsetLainnyaModal(rid) {
    _alActiveRid = rid;
    var info = _rowAkunInfo[rid] || {};
    document.getElementById('saModalAsetLainnyaAkunNama').textContent = info.nama || '';
    _clearAsetLainnyaRows();
    var existing = _rowDetailMap[rid];
    if (existing && existing.detail_rows && existing.detail_rows.length) {
      existing.detail_rows.forEach(function (d) { asetLainnyaAddRow(d); });
    } else {
      asetLainnyaAddRow();
    }
    document.getElementById('saModalAsetLainnyaBackdrop').classList.add('ni-modal-backdrop--visible');
  }

  function closeAsetLainnyaModal() {
    document.getElementById('saModalAsetLainnyaBackdrop').classList.remove('ni-modal-backdrop--visible');
    _alActiveRid = null;
  }

  function _clearAsetLainnyaRows() {
    _alTomSelects.forEach(function (ts) { try { ts.destroy(); } catch (e) {} });
    _alTomSelects = [];
    document.getElementById('saModalAsetLainnyaRows').innerHTML = '';
    _alRowCount = 0;
    _updateAsetLainnyaTotal();
  }

  function asetLainnyaAddRow(prefill) {
    _alRowCount++;
    var mrid = _alRowCount;
    var tbody = document.getElementById('saModalAsetLainnyaRows');
    var tr = document.createElement('tr');
    tr.id = 'al_modal_row_' + mrid;
    tr.innerHTML =
      '<td><select id="al_modal_item_' + mrid + '" placeholder="Ketik item…"></select></td>' +
      '<td><input type="number" id="al_modal_qty_' + mrid + '" class="ni-jm-input" min="0.0001" step="0.0001" value="0" oninput="saAsetLainnyaUpdateRow(' + mrid + ')"></td>' +
      '<td><input type="number" id="al_modal_hpp_' + mrid + '" class="ni-jm-input" min="0" step="1" value="0" oninput="saAsetLainnyaUpdateRow(' + mrid + ')"></td>' +
      '<td><button type="button" class="ni-btn ni-btn--outline-danger ni-btn--sm" onclick="saModalAsetLainnyaRemoveRow(' + mrid + ')" style="padding:4px 8px;"><i data-lucide="trash-2" style="width:12px;height:12px"></i></button></td>';
    tbody.appendChild(tr);

    var currentMrid = mrid;
    var ebLv1 = _getEBLv1Id();
    var ts = new TomSelect('#al_modal_item_' + mrid, {
      valueField: 'id', labelField: 'text', searchField: 'text',
      options: [], maxOptions: false, placeholder: 'Ketik kode/nama item…',
      preload: 'focus', shouldLoad: function () { return false; },
      load: function (query, callback) {
        var url = cfg.itemAutocompleteUrl + '?term=' + encodeURIComponent(query);
        if (ebLv1) url += '&eb_lv1_id=' + encodeURIComponent(ebLv1);
        fetch(url).then(function (r) { return r.json(); }).then(function (data) { callback(data); }).catch(function () { callback(); });
      },
      onChange: function () { _updateAsetLainnyaTotal(); },
      create: function (input, callback) {
        openItemModal(input, function (newOpt) {
          var selEl = document.getElementById('al_modal_item_' + currentMrid);
          if (selEl && selEl.tomselect) { selEl.tomselect.addOption(newOpt); selEl.tomselect.setValue(newOpt.id, true); }
        }, 'ALL');
        callback();
      },
      createFilter: function (input) { return input.trim().length >= 2; },
      render: { option_create: function (data, escape) { return '<div class="create">Tambah item baru: <strong>' + escape(data.input) + '</strong></div>'; } },
      dropdownParent: 'body',
    });
    _alTomSelects.push(ts);

    if (prefill) {
      if (prefill.item_id) { var opt = { id: String(prefill.item_id), text: prefill.item_text || String(prefill.item_id) }; ts.addOption(opt); ts.setValue(String(prefill.item_id), true); }
      if (prefill.qty) document.getElementById('al_modal_qty_' + mrid).value = prefill.qty;
      if (prefill.unit_price) document.getElementById('al_modal_hpp_' + mrid).value = prefill.unit_price;
      _updateAsetLainnyaTotal();
    }
    lucide.createIcons();
    _updateAsetLainnyaTotal();
  }

  function asetLainnyaRemoveRow(mrid) {
    var tr = document.getElementById('al_modal_row_' + mrid);
    if (!tr) return;
    var sel = document.getElementById('al_modal_item_' + mrid);
    if (sel && sel.tomselect) {
      var idx = _alTomSelects.indexOf(sel.tomselect);
      if (idx !== -1) _alTomSelects.splice(idx, 1);
      sel.tomselect.destroy();
    }
    tr.remove();
    _updateAsetLainnyaTotal();
  }

  function _updateAsetLainnyaTotal() {
    var total = 0;
    document.querySelectorAll('#saModalAsetLainnyaRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('al_modal_row_', '');
      var qty = parseFloat((document.getElementById('al_modal_qty_' + mrid) || {}).value || 0);
      var hpp = parseFloat((document.getElementById('al_modal_hpp_' + mrid) || {}).value || 0);
      total += qty * hpp;
    });
    var el = document.getElementById('saModalAsetLainnyaTotal');
    if (el) el.textContent = 'Rp ' + formatNum(total);
  }

  function _collectAsetLainnyaRows() {
    var results = [];
    document.querySelectorAll('#saModalAsetLainnyaRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('al_modal_row_', '');
      var selEl = document.getElementById('al_modal_item_' + mrid);
      var qty = parseFloat((document.getElementById('al_modal_qty_' + mrid) || {}).value || 0);
      var hpp = parseFloat((document.getElementById('al_modal_hpp_' + mrid) || {}).value || 0);
      if (!selEl || !selEl.value || qty <= 0 || hpp < 0) return;
      var ts = selEl.tomselect;
      var opt = ts ? ts.options[selEl.value] : null;
      results.push({ item_id: selEl.value, item_text: opt ? opt.text : String(selEl.value), qty: qty, unit_price: hpp, total: qty * hpp });
    });
    return results;
  }

  function confirmAsetLainnyaDetail() {
    var rid = _alActiveRid;
    if (!rid) return;
    var detailRows = _collectAsetLainnyaRows();
    if (!detailRows.length) { alert('Minimal 1 aset lainnya harus diisi dengan item, qty > 0, dan nilai perolehan valid.'); return; }
    var grandTotal = detailRows.reduce(function (s, r) { return s + r.total; }, 0);
    _rowDetailMap[rid] = { type: 'aset_lainnya', detail_rows: detailRows };
    if (cfg.onDebitConfirmed) cfg.onDebitConfirmed(rid, grandTotal);
    _updateDetailBadge(rid);
    closeAsetLainnyaModal();
  }

  // ── Modal Disetor modal ───────────────────────────────────────────────────
  function openModalDisetorModal(rid) {
    _mdActiveRid = rid;
    var info = _rowAkunInfo[rid] || {};
    document.getElementById('saModalDisetorAkunNama').textContent = info.nama || '';
    document.getElementById('saModalDisetorRows').innerHTML = '';
    _mdRowCount = 0;
    var existing = _rowDetailMap[rid];
    if (existing && existing.detail_rows && existing.detail_rows.length) {
      existing.detail_rows.forEach(function (d) { modalDisetorAddRow(d); });
    } else {
      modalDisetorAddRow();
    }
    document.getElementById('saModalDisetorBackdrop').classList.add('ni-modal-backdrop--visible');
    _updateModalDisetorTotal();
  }

  function closeModalDisetorModal() {
    document.getElementById('saModalDisetorBackdrop').classList.remove('ni-modal-backdrop--visible');
    _mdActiveRid = null;
  }

  function modalDisetorAddRow(prefill) {
    _mdRowCount++;
    var mrid = _mdRowCount;
    var tbody = document.getElementById('saModalDisetorRows');
    var tr = document.createElement('tr');
    tr.id = 'md_modal_row_' + mrid;
    var nama = (prefill && prefill.nama_pemilik) ? prefill.nama_pemilik : '';
    var jumlah = (prefill && prefill.jumlah) ? prefill.jumlah : 0;
    var ket = (prefill && prefill.keterangan) ? prefill.keterangan : '';
    tr.innerHTML =
      '<td><input type="text" id="md_m_nama_' + mrid + '" class="ni-jm-input" placeholder="Nama pemilik..." value="' + nama.replace(/"/g, '&quot;') + '"></td>' +
      '<td><input type="number" id="md_m_jumlah_' + mrid + '" class="ni-jm-input" min="0" step="1" value="' + jumlah + '" oninput="saUpdateModalDisetorTotal()"></td>' +
      '<td><input type="text" id="md_m_ket_' + mrid + '" class="ni-jm-input" placeholder="Opsional" value="' + ket.replace(/"/g, '&quot;') + '"></td>' +
      '<td><button type="button" class="ni-btn ni-btn--outline-danger ni-btn--sm" onclick="saModalDisetorRemoveRow(' + mrid + ')" style="padding:4px 8px;"><i data-lucide="trash-2" style="width:12px;height:12px"></i></button></td>';
    tbody.appendChild(tr);
    lucide.createIcons();
  }

  function modalDisetorRemoveRow(mrid) {
    var tr = document.getElementById('md_modal_row_' + mrid);
    if (tr) tr.remove();
    _updateModalDisetorTotal();
  }

  function _updateModalDisetorTotal() {
    var total = 0;
    document.querySelectorAll('#saModalDisetorRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('md_modal_row_', '');
      var inp = document.getElementById('md_m_jumlah_' + mrid);
      if (inp) total += parseFloat(inp.value || 0);
    });
    var el = document.getElementById('saModalDisetorTotal');
    if (el) el.textContent = 'Rp ' + formatNum(total);
  }

  function confirmModalDisetorDetail() {
    var rows = [];
    document.querySelectorAll('#saModalDisetorRows tr').forEach(function (tr) {
      var mrid = tr.id.replace('md_modal_row_', '');
      var nama = ((document.getElementById('md_m_nama_' + mrid) || {}).value || '').trim();
      var jumlah = parseFloat((document.getElementById('md_m_jumlah_' + mrid) || {}).value || 0);
      var ket = ((document.getElementById('md_m_ket_' + mrid) || {}).value || '').trim();
      if (nama && jumlah > 0) rows.push({ nama_pemilik: nama, jumlah: jumlah, keterangan: ket });
    });
    if (!rows.length) { alert('Tambahkan minimal satu pemilik dengan jumlah modal > 0.'); return; }
    var total = rows.reduce(function (s, r) { return s + r.jumlah; }, 0);
    if (_mdActiveRid !== null) {
      _rowDetailMap[_mdActiveRid] = { type: 'modal_disetor', detail_rows: rows };
      _updateDetailBadge(_mdActiveRid);
      if (cfg.onKreditConfirmed) cfg.onKreditConfirmed(_mdActiveRid, total);
    }
    closeModalDisetorModal();
  }

  // ── Modal tipe item change ────────────────────────────────────────────────
  function onModalTipeItemChange() {
    var tipe = (document.getElementById('modal_tipe_item') || {}).value || '';
    var isInventory = (tipe === 'RM' || tipe === 'FG' || tipe === 'ITM' || tipe === 'RMB' || tipe === 'FGB' || tipe === 'ITMB');
    var invEl = document.getElementById('modal_inventory_fields');
    var atpEl = document.getElementById('modal_atp_fields');
    var allEl = document.getElementById('modal_all_fields');
    if (invEl) invEl.style.display = isInventory ? '' : 'none';
    if (atpEl) atpEl.style.display = (tipe === 'ATP') ? '' : 'none';
    if (allEl) allEl.style.display = (tipe === 'ALL') ? '' : 'none';
    var titles = {
      RM: 'Tambah Raw Material', FG: 'Tambah Finished Good', ITM: 'Tambah Item Lainnya',
      RMB: 'Tambah Raw Material Bulk', FGB: 'Tambah Finished Good Bulk', ITMB: 'Tambah Item Lainnya Bulk',
      ATP: 'Tambah Aset Tetap', ALL: 'Tambah Aset Lainnya',
    };
    var titleEl = document.getElementById('saItemModalTitle');
    if (titleEl) titleEl.textContent = titles[tipe] || 'Tambah Item Baru';
    loadModalKategori(tipe, _getEBLv1Id());
  }

  // ── Row update helper (persediaan) ────────────────────────────────────────
  function modalUpdateRow(mrid) {
    var qty = parseFloat((document.getElementById('modal_qty_' + mrid) || {}).value || 0);
    var hp = parseFloat((document.getElementById('modal_unit_price_' + mrid) || {}).value || 0);
    var totalEl = document.getElementById('modal_total_' + mrid);
    if (totalEl) totalEl.value = qty * hp;
    _updatePersediaanTotal();
  }

  // ── Public API ────────────────────────────────────────────────────────────
  var niDetailModals = {
    init: function (config) {
      cfg = config;
      AKUN_DETAIL_MAP = config.akunDetailMap || {};
      _rowDetailMap = {};
      _rowAkunInfo = {};
    },
    onAkunChange: _onAkunChange,
    clearRow: function (rid) {
      delete _rowDetailMap[rid];
      delete _rowAkunInfo[rid];
      var wrapEl = document.getElementById('detail_wrap_' + rid);
      if (wrapEl) wrapEl.style.display = 'none';
      _updateDetailBadge(rid);
    },
    prefillRow: function (rid, detailType, detailRows) {
      _rowDetailMap[rid] = { type: detailType, detail_rows: detailRows };
      _updateDetailBadge(rid);
    },
    getRowDetailMap: function () { return _rowDetailMap; },
    updateDetailBadge: _updateDetailBadge,
    getDetailTypeForAkun: _getDetailTypeForAkun,
  };

  window.niDetailModals = niDetailModals;

  // ── Backward-compat window.sa* exports ───────────────────────────────────
  window.saOpenDetailModal = openPersediaanModal;
  window.saCloseDetailModal = closePersediaanModal;
  window.saConfirmDetail = confirmPersediaanDetail;
  window.saModalAddRow = modalAddRow;
  window.saModalRemoveRow = modalRemoveRow;
  window.saModalUpdateRow = modalUpdateRow;

  window.saOpenItemModal = openItemModal;
  window.saCloseItemModal = closeItemModal;
  window.saSubmitItemModal = submitItemModal;
  window.saOnModalTipeItemChange = onModalTipeItemChange;

  window.saOpenKategoriModal = openKategoriModal;
  window.saCloseKategoriModal = closeKategoriModal;
  window.saSubmitKategoriModal = submitKategoriModal;

  window.saOpenAsetTetapModal = openAsetTetapModal;
  window.saCloseAsetTetapModal = closeAsetTetapModal;
  window.saConfirmAsetTetapDetail = confirmAsetTetapDetail;
  window.saModalAsetTetapAddRow = asetTetapAddRow;
  window.saModalAsetTetapRemoveRow = asetTetapRemoveRow;
  window.saAsetTetapUpdateRow = function (mrid) { _updateAsetTetapTotal(); };

  window.saOpenAsetLainnyaModal = openAsetLainnyaModal;
  window.saCloseAsetLainnyaModal = closeAsetLainnyaModal;
  window.saConfirmAsetLainnyaDetail = confirmAsetLainnyaDetail;
  window.saModalAsetLainnyaAddRow = asetLainnyaAddRow;
  window.saModalAsetLainnyaRemoveRow = asetLainnyaRemoveRow;
  window.saAsetLainnyaUpdateRow = function (mrid) { _updateAsetLainnyaTotal(); };

  window.saOpenModalDisetorModal = openModalDisetorModal;
  window.saCloseModalDisetorModal = closeModalDisetorModal;
  window.saConfirmModalDisetorDetail = confirmModalDisetorDetail;
  window.saModalDisetorAddRow = modalDisetorAddRow;
  window.saModalDisetorRemoveRow = modalDisetorRemoveRow;
  window.saUpdateModalDisetorTotal = _updateModalDisetorTotal;

})();
