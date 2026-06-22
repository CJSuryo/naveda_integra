/* Reusable piutang wizard. Call initPiutangForm(rootEl, options). */
function initPiutangForm(root, options) {
  options = options || {};

  /* ── Standar callout content ─────────────────────────────────── */
  var CALLOUTS = {
    '': {
      color: 'var(--ni-border)', bg: 'var(--ni-surface-alt,#f5f5f5)',
      html: '<strong>Belum ada entitas bisnis dipilih.</strong> Pilih entitas bisnis — standar akan mengikuti pengaturannya. Atau pilih standar secara eksplisit di dropdown di atas.'
    },
    'psak': {
      color: '#2563eb', bg: '#eff6ff',
      html: '<strong style="color:#1d4ed8">SAK — Full IFRS / PSAK 71</strong><br>Standar penuh untuk entitas publik dan perusahaan besar.<br><div style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:.87em"><span>✅ Amortised Cost + EIR (Suku Bunga Efektif)</span><span>✅ ECL 3-Stage (Stage 1/2/3 berdasarkan DPD)</span><span>✅ Biaya transaksi dikapitalisasi</span><span>✅ Modification accounting (gain/loss)</span><span>✅ Factoring &amp; derecognition analysis</span><span>✅ Reklasifikasi bagian lancar otomatis</span><span>✅ ECL General Approach (PD × LGD × EAD)</span><span>✅ Net carrying EIR Stage 3</span></div>'
    },
    'sak_ep': {
      color: '#d97706', bg: '#fffbeb',
      html: '<strong style="color:#b45309">SAK EP — Entitas Privat</strong><br>Standar disederhanakan untuk entitas privat (IFRS for SMEs equivalent).<br><div style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:.87em"><span>✅ Amortised Cost + EIR</span><span>✅ Biaya transaksi dikapitalisasi</span><span>✅ ECL Simplified (aging matrix)</span><span>✅ Modification accounting</span><span>✅ Factoring analysis</span><span>✅ Reklasifikasi bagian lancar</span><span>❌ Tanpa ECL General Approach 3-stage</span><span>❌ Tanpa net carrying EIR Stage 3</span></div>'
    },
    'sak_emkm': {
      color: '#6b7280', bg: '#f9fafb',
      html: '<strong style="color:#374151">SAK EMKM — Entitas Mikro, Kecil, Menengah</strong><br>Standar paling sederhana. Tidak ada amortisasi EIR — piutang dicatat pada biaya perolehan (nominal).<br><div style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:.87em"><span>✅ Biaya perolehan / historical cost</span><span>✅ Penyisihan sederhana (aging matrix, opsional)</span><span>❌ Tanpa EIR / amortisasi PV</span><span>❌ Tanpa biaya transaksi kapitalisasi</span><span>❌ Tanpa ECL General Approach</span><span>❌ Tanpa modification / factoring accounting</span></div>'
    }
  };

  var EB_STANDAR_MAP = options.ebStandarMap || {};
  var EB_LABEL_MAP = { 'psak': 'SAK (Full IFRS)', 'sak_ep': 'SAK EP', 'sak_emkm': 'SAK EMKM' };
  var ebOptions  = options.ebOptions  || [];
  var ebSelected = options.ebSelected || '';

  var $ = function(sel) { return root.querySelector(sel); };
  var $$ = function(sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); };

  var standarEl   = $('#id_standar_akuntansi');
  var calloutEl   = $('#standar-callout');
  var ebHintEl    = $('#eb-standar-hint');
  var bungaCard   = $('#bunga-angsuran-card');
  var pvCard      = $('#pv-setup-card');
  var biayaCard   = $('#biaya-agunan-card');
  var biayaTxGrp  = $('#biaya-transaksi-group');
  var klasCard    = $('#klasifikasi-card');
  var klasWizard  = $('#klasifikasi-wizard');
  var klasEmkm    = $('#klasifikasi-emkm');
  var klasBadge   = $('#klasifikasi-standar-badge');
  var jwtEl       = $('#id_jenis_jangka_waktu');
  var bungaEl     = $('#id_jenis_bunga');
  var sukuGrp     = $('#suku-bunga-group');
  var ebSelect    = $('#id_eb_selection');

  /* ── Hidden form fields (set by JS) ─────────────────────────── */
  var kategoriHidden = $('#id_kategori_pengukuran');
  var bmHidden       = $('#id_business_model');
  var sppiHidden     = $('#id_sppi_test_passed');

  /* ── State ────────────────────────────────────────────────────── */
  var selectedBM   = bmHidden   ? bmHidden.value   : '';
  var selectedSPPI = sppiHidden ? sppiHidden.value  : '';

  /* ── Helpers ──────────────────────────────────────────────────── */
  function getEffective() {
    var override = standarEl ? standarEl.value : '';
    if (override) return override;
    var ebVal = ebSelect ? ebSelect.value : '';
    return EB_STANDAR_MAP[ebVal] || '';
  }

  /* ── Classification logic ─────────────────────────────────────── */
  var RESULT_CONFIGS = {
    'amortised_cost': {
      color: '#16a34a', bg: '#f0fdf4',
      html: '<span style="font-size:1.1em">✅</span> <strong style="color:#15803d">Biaya Perolehan Diamortisasi (Amortised Cost)</strong><br><span style="font-size:.84em;color:var(--ni-text-muted)">Piutang diukur pada biaya perolehan diamortisasi menggunakan Suku Bunga Efektif (EIR). Fitur lengkap tersedia: EIR, ECL staging, modification accounting, factoring analysis.</span>'
    },
    'fvoci': {
      color: '#d97706', bg: '#fffbeb',
      html: '<span style="font-size:1.1em">⚠️</span> <strong style="color:#b45309">Nilai Wajar Melalui OCI (FVOCI)</strong><br><span style="font-size:.84em;color:var(--ni-text-muted)">Piutang diukur pada nilai wajar, perubahan dicatat di OCI. <em>Catatan: modul ini saat ini hanya mendukung Amortised Cost secara penuh. FVOCI akan dicatat sebagai Amortised Cost untuk sementara.</em></span>'
    },
    'fvpl': {
      color: '#dc2626', bg: '#fef2f2',
      html: '<span style="font-size:1.1em">❌</span> <strong style="color:#b91c1c">Nilai Wajar Melalui Laba Rugi (FVPL)</strong><br><span style="font-size:.84em;color:var(--ni-text-muted)">Piutang diukur pada nilai wajar, seluruh perubahan diakui di laba rugi. <em>Catatan: modul ini saat ini hanya mendukung Amortised Cost secara penuh. FVPL akan dicatat sebagai Amortised Cost untuk sementara.</em></span>'
    },
    '': {
      color: 'var(--ni-border)', bg: 'var(--ni-surface-alt)',
      html: '<span class="ni-text-muted">← Pilih Business Model dan SPPI Test di atas untuk menentukan kategori pengukuran secara otomatis.</span>'
    }
  };

  function computeKategori(bm, sppi, standar) {
    if (standar === 'sak_emkm') return 'amortised_cost';
    if (!bm) return '';
    if (bm === 'other') return 'fvpl';
    if (sppi === 'False') return 'fvpl';
    if (sppi !== 'True') return ''; // belum diuji
    if (bm === 'hold_to_collect') return 'amortised_cost';
    if (bm === 'hold_to_collect_and_sell') return 'fvoci';
    return '';
  }

  function updateKlasifikasiResult() {
    var standar   = getEffective();
    var kat       = computeKategori(selectedBM, selectedSPPI, standar);
    var cfg       = RESULT_CONFIGS[kat] || RESULT_CONFIGS[''];
    var resultEl  = $('#klasifikasi-result');
    var contentEl = $('#klasifikasi-result-content');
    var sppiSec   = $('#sppi-section');
    if (resultEl)  { resultEl.style.borderColor = cfg.color; resultEl.style.background = cfg.bg; }
    if (contentEl) contentEl.innerHTML = cfg.html;
    if (kategoriHidden) kategoriHidden.value = kat || 'amortised_cost';
    // Hide SPPI section when BM=other — result is always FVPL regardless of SPPI
    if (sppiSec) sppiSec.style.display = (selectedBM === 'other') ? 'none' : '';
  }

  /* ── Business Model card selection ───────────────────────────── */
  $$('.bm-option').forEach(function(card) {
    card.addEventListener('click', function() {
      selectedBM = this.dataset.value;
      if (bmHidden) bmHidden.value = selectedBM;
      $$('.bm-option').forEach(function(c) {
        var active = c.dataset.value === selectedBM;
        c.style.borderColor  = active ? '#2563eb' : 'var(--ni-border)';
        c.style.background   = active ? '#eff6ff' : '';
        c.style.boxShadow    = active ? '0 0 0 3px rgba(37,99,235,.15)' : '';
      });
      updateKlasifikasiResult();
    });
    // Restore state on load
    if (selectedBM && card.dataset.value === selectedBM) {
      card.style.borderColor = '#2563eb';
      card.style.background  = '#eff6ff';
      card.style.boxShadow   = '0 0 0 3px rgba(37,99,235,.15)';
    }
  });

  /* ── SPPI option selection ────────────────────────────────────── */
  $$('.sppi-option').forEach(function(card) {
    card.addEventListener('click', function() {
      selectedSPPI = this.dataset.value;
      if (sppiHidden) sppiHidden.value = selectedSPPI;
      $$('.sppi-option').forEach(function(c) {
        var active = c.dataset.value === selectedSPPI;
        c.style.borderColor = active ? '#2563eb' : 'var(--ni-border)';
        c.style.background  = active ? '#eff6ff' : '';
        c.style.boxShadow   = active ? '0 0 0 3px rgba(37,99,235,.15)' : '';
      });
      updateKlasifikasiResult();
    });
    // Restore state on load
    if (card.dataset.value === selectedSPPI) {
      card.style.borderColor = '#2563eb';
      card.style.background  = '#eff6ff';
      card.style.boxShadow   = '0 0 0 3px rgba(37,99,235,.15)';
    }
  });

  /* ── Update callout and all section visibility ─────────────────── */
  function updateCallout() {
    if (!calloutEl) return;
    var s = getEffective();
    var cfg = CALLOUTS[s] || CALLOUTS[''];
    calloutEl.style.background  = cfg.bg;
    calloutEl.style.borderColor = cfg.color;
    calloutEl.innerHTML         = cfg.html;
  }

  function updateEbHint() {
    if (!ebHintEl) return;
    var ebVal = ebSelect ? ebSelect.value : '';
    var ebSt  = EB_STANDAR_MAP[ebVal];
    if (ebSt && !(standarEl && standarEl.value)) {
      ebHintEl.style.display = '';
      ebHintEl.innerHTML = '&#x2139;&#xFE0F; Entitas bisnis ini menggunakan <strong>' + (EB_LABEL_MAP[ebSt] || ebSt) + '</strong>. Standar piutang akan mengikutinya secara otomatis.';
    } else if (ebSt && standarEl && standarEl.value && standarEl.value !== ebSt) {
      ebHintEl.style.display = '';
      ebHintEl.innerHTML = '&#x26A0;&#xFE0F; Entitas bisnis menggunakan <strong>' + (EB_LABEL_MAP[ebSt] || ebSt) + '</strong>, tapi piutang ini dioverride ke <strong>' + (EB_LABEL_MAP[standarEl.value] || standarEl.value) + '</strong>.';
    } else {
      ebHintEl.style.display = 'none';
    }
  }

  function updateSections() {
    var s       = getEffective();
    var isEmkm  = s === 'sak_emkm';
    var isLongT = jwtEl && jwtEl.value === 'long_term';

    // Klasifikasi card: show always, but switch between EMKM info and full wizard
    if (klasWizard) klasWizard.style.display = isEmkm ? 'none' : '';
    if (klasEmkm)   klasEmkm.style.display   = isEmkm ? ''     : 'none';
    if (klasBadge) {
      if (s === 'psak')      { klasBadge.className = 'ni-badge ni-badge--primary'; klasBadge.textContent = 'PSAK 71'; }
      else if (s === 'sak_ep') { klasBadge.className = 'ni-badge ni-badge--warning'; klasBadge.textContent = 'SAK EP'; }
      else if (s === 'sak_emkm') { klasBadge.className = 'ni-badge ni-badge--secondary'; klasBadge.textContent = 'SAK EMKM'; }
      else { klasBadge.textContent = ''; }
    }

    if (bungaCard) bungaCard.style.display = isLongT ? '' : 'none';
    if (pvCard)    pvCard.style.display    = (isLongT && !isEmkm) ? '' : 'none';
    if (biayaCard) biayaCard.style.display = !isEmkm ? '' : 'none';
    if (biayaTxGrp) biayaTxGrp.style.display = isEmkm ? 'none' : '';

    if (bungaEl && sukuGrp) {
      sukuGrp.style.display = bungaEl.value === 'tanpa_bunga' ? 'none' : '';
    }

    // For EMKM, force kategori to amortised_cost
    if (isEmkm && kategoriHidden) kategoriHidden.value = 'amortised_cost';

    updateKlasifikasiResult();
  }

  function updateAll() {
    updateCallout();
    updateEbHint();
    updateSections();
  }

  if (standarEl) standarEl.addEventListener('change', updateAll);
  if (jwtEl)    jwtEl.addEventListener('change',    updateAll);
  if (bungaEl)  bungaEl.addEventListener('change',  updateAll);

  /* ── Entitas Bisnis TomSelect ─────────────────────────────────── */
  if (ebSelect && ebOptions.length) {
    ebOptions.forEach(function(opt) {
      var o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label;
      if (opt.value === ebSelected) o.selected = true;
      ebSelect.appendChild(o);
    });
    if (typeof TomSelect !== 'undefined') {
      var ebTS = new TomSelect(ebSelect, {
        maxOptions: 500,
        placeholder: '— Pilih Entitas Bisnis (opsional) —',
        allowEmptyOption: true,
        onChange: function() { updateAll(); }
      });
    } else {
      ebSelect.addEventListener('change', updateAll);
    }
  }

  /* ── Akun TomSelect ───────────────────────────────────────────── */
  if (typeof TomSelect !== 'undefined') {
    ['#id_coa_piutang_account','#id_interest_income_account','#id_coa_piutang_lancar_account','#id_biaya_transaksi_account'].forEach(function(sel) {
      var el = $(sel);
      if (el) new TomSelect(el, { allowEmptyOption: true, maxOptions: 1000 });
    });
  }

  /* ── Detail rows ──────────────────────────────────────────────── */
  var tbody     = $('#detail-tbody');
  var addBtn    = $('#add-detail-row');
  var totalFrms = $('#id_details-TOTAL_FORMS');

  if (!tbody) return; // embedded mode: no detail table, stop here

  function updateTotal() {
    var total = 0;
    $$('.amount-field').forEach(function(inp) {
      var row = inp.closest('tr');
      var cb  = row ? row.querySelector('input[type=checkbox][name$="-DELETE"]') : null;
      if (!cb || !cb.checked) total += parseFloat(inp.value) || 0;
    });
    var el = $('#detail-total');
    if (el) el.textContent = total.toLocaleString('id-ID');
  }

  function attachRow(row) {
    row.querySelector('.remove-row').addEventListener('click', function() {
      var cb = row.querySelector('input[type=checkbox][name$="-DELETE"]');
      if (cb) { cb.checked = true; row.classList.add('ni-row--deleted'); }
      else    { row.remove(); totalFrms.value = parseInt(totalFrms.value) - 1; }
      updateTotal();
    });
    var amt = row.querySelector('.amount-field');
    if (amt) amt.addEventListener('input', updateTotal);
  }

  $$('.detail-row').forEach(attachRow);
  updateTotal();

  if (addBtn) {
    addBtn.addEventListener('click', function() {
      var idx    = parseInt(totalFrms.value);
      var first  = tbody.querySelector('.detail-row');
      var newRow = first ? first.cloneNode(true) : null;
      if (!newRow) return;
      newRow.querySelectorAll('input, select').forEach(function(el) {
        el.name = el.name.replace(/-\d+-/, '-' + idx + '-');
        el.id   = el.id.replace(/_\d+_/, '_' + idx + '_');
        if (el.type !== 'checkbox') el.value = '';
        if (el.type === 'checkbox') el.checked = false;
      });
      newRow.classList.remove('ni-row--deleted');
      tbody.appendChild(newRow);
      totalFrms.value = idx + 1;
      attachRow(newRow);
    });
  }

  /* ── Initial render ───────────────────────────────────────────── */
  updateAll();
}
