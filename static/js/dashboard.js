/**
 * Naveda Integra — dashboard.js
 * Isolated AJAX-per-widget dashboard with Chart.js and custom HTML tooltips.
 */
(function () {
  'use strict';

  // ── EB state (set from template via window._dashEbInit) ──────────────────
  var ebState = {
    eb_id: null,
    eb_lv2_id: null,
    eb_lv3_id: null
  };

  function getEbParams() {
    var p = '';
    if (ebState.eb_id)     p += '&eb_id='     + ebState.eb_id;
    if (ebState.eb_lv2_id) p += '&eb_lv2_id=' + ebState.eb_lv2_id;
    if (ebState.eb_lv3_id) p += '&eb_lv3_id=' + ebState.eb_lv3_id;
    return p;
  }

  function initEbState() {
    var init = window._dashEbInit;
    if (!init) return;
    ebState.eb_id     = init.eb_id     || null;
    ebState.eb_lv2_id = init.eb_lv2_id || null;
    ebState.eb_lv3_id = init.eb_lv3_id || null;
  }

  // ── Colors ────────────────────────────────────────────────────────────────
  var C = {
    blue:   '#0054a6',
    green:  '#10b981',
    amber:  '#f59e0b',
    red:    '#ef4444',
    purple: '#8b5cf6',
    teal:   '#06b6d4',
    muted:  '#94a3b8',
    border: '#e2e8f0',
    bg:     '#f8fafc',
    multi: ['#0054a6','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4']
  };

  // ── IDR formatter ─────────────────────────────────────────────────────────
  function fmtIDR(val) {
    if (val >= 1e9)  return 'Rp ' + (val / 1e9).toFixed(1).replace('.0','') + 'M';
    if (val >= 1e6)  return 'Rp ' + (val / 1e6).toFixed(1).replace('.0','') + 'jt';
    if (val >= 1e3)  return 'Rp ' + (val / 1e3).toFixed(0) + 'rb';
    return 'Rp ' + Math.round(val).toLocaleString('id-ID');
  }

  function fmtNum(val) {
    return Number(val).toLocaleString('id-ID', { maximumFractionDigits: 2 });
  }

  // ── Tooltip factory ────────────────────────────────────────────────────────
  // Returns a Chart.js external tooltip handler that builds a rich HTML tooltip.
  function makeTooltipHandler(contextFn) {
    return function (context) {
      var tooltipModel = context.tooltip;
      var id = context.chart.canvas.id + '-tooltip';
      var el = document.getElementById(id);

      if (!el) {
        el = document.createElement('div');
        el.id = id;
        el.className = 'ni-chart-tooltip';
        el.style.cssText = 'position:absolute;pointer-events:none;transition:opacity 0.15s;z-index:100;min-width:160px;';
        context.chart.canvas.parentNode.style.position = 'relative';
        context.chart.canvas.parentNode.appendChild(el);
      }

      if (tooltipModel.opacity === 0) {
        el.style.opacity = '0';
        return;
      }

      var title = tooltipModel.title ? tooltipModel.title[0] : '';
      var rows = tooltipModel.dataPoints || [];
      var contextHtml = contextFn ? contextFn(rows, tooltipModel) : '';

      var rowsHtml = rows.map(function (p) {
        var color = p.dataset.borderColor || p.dataset.backgroundColor || C.blue;
        var rawVal = p.raw;
        var label = p.dataset.label || '';
        var formatted = typeof rawVal === 'number' && label.toLowerCase().indexOf('%') === -1
          ? (label.toLowerCase().indexOf('margin') !== -1 || label.toLowerCase().indexOf('%') !== -1
              ? fmtNum(rawVal) + '%'
              : fmtIDR(rawVal))
          : fmtNum(rawVal);
        return '<div class="ni-chart-tooltip__row">' +
          '<span class="ni-chart-tooltip__color" style="background:' + color + '"></span>' +
          '<span class="ni-chart-tooltip__label">' + label + '</span>' +
          '<span class="ni-chart-tooltip__value">' + formatted + '</span>' +
          '</div>';
      }).join('');

      el.innerHTML =
        '<div class="ni-chart-tooltip__title">' + title + '</div>' +
        rowsHtml +
        (contextHtml ? '<div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.12);font-size:0.6875rem;color:#94a3b8;">' + contextHtml + '</div>' : '');

      var pos = context.chart.canvas.getBoundingClientRect();
      var canvasParent = context.chart.canvas.parentNode;
      var parentRect = canvasParent.getBoundingClientRect();

      var x = tooltipModel.caretX;
      var y = tooltipModel.caretY;

      // Keep tooltip inside parent
      var tipW = 200;
      if (x + tipW + 10 > canvasParent.offsetWidth) {
        x = x - tipW - 10;
      } else {
        x = x + 10;
      }

      el.style.left = x + 'px';
      el.style.top = (y - 10) + 'px';
      el.style.opacity = '1';
    };
  }

  // ── Base chart options ────────────────────────────────────────────────────
  function baseOptions(tooltipHandler) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            usePointStyle: true,
            pointStyle: 'rectRounded',
            padding: 16,
            font: { family: "'Inter', sans-serif", size: 11 }
          }
        },
        tooltip: {
          enabled: false,
          external: tooltipHandler || makeTooltipHandler(null)
        }
      },
      animation: { duration: 350, easing: 'easeOutQuart' }
    };
  }

  // ── Chart registry ─────────────────────────────────────────────────────────
  var charts = {};

  function destroyChart(id) {
    if (charts[id]) {
      charts[id].destroy();
      delete charts[id];
    }
  }

  function renderLineChart(canvasId, labels, datasets, opts) {
    destroyChart(canvasId);
    var ctx = document.getElementById(canvasId);
    if (!ctx) return;
    var options = Object.assign({}, baseOptions(opts && opts.tooltipHandler), {
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: "'Inter', sans-serif", size: 10 }, maxRotation: 0 }
        },
        y: {
          beginAtZero: true,
          grid: { color: C.border },
          ticks: {
            font: { family: "'Inter', sans-serif", size: 10 },
            callback: function (v) { return fmtIDR(v); }
          }
        }
      },
      elements: {
        line: { tension: 0.35, borderWidth: 2.5 },
        point: { radius: 3, hoverRadius: 6 }
      }
    });
    if (opts && opts.yCallback) {
      options.scales.y.ticks.callback = opts.yCallback;
    }
    charts[canvasId] = new Chart(ctx, { type: 'line', data: { labels: labels, datasets: datasets }, options: options });
  }

  function renderBarChart(canvasId, labels, datasets, opts) {
    destroyChart(canvasId);
    var ctx = document.getElementById(canvasId);
    if (!ctx) return;
    var isHorizontal = !!(opts && opts.horizontal);
    var scales;
    if (isHorizontal) {
      // indexAxis:'y' → x = value axis, y = category axis
      scales = {
        x: {
          beginAtZero: true,
          grid: { color: C.border },
          ticks: {
            font: { family: "'Inter', sans-serif", size: 10 },
            callback: (opts && opts.xCallback) || function(v) { return fmtNum(v); }
          }
        },
        y: {
          grid: { display: false },
          ticks: { font: { family: "'Inter', sans-serif", size: 10 } }
        }
      };
    } else {
      scales = {
        x: {
          grid: { display: false },
          ticks: { font: { family: "'Inter', sans-serif", size: 10 }, maxRotation: 0 }
        },
        y: {
          beginAtZero: true,
          grid: { color: C.border },
          ticks: {
            font: { family: "'Inter', sans-serif", size: 10 },
            callback: (opts && opts.yCallback) || function(v) { return fmtIDR(v); }
          }
        }
      };
    }
    var options = Object.assign({}, baseOptions(opts && opts.tooltipHandler), {
      indexAxis: isHorizontal ? 'y' : 'x',
      scales: scales,
      borderRadius: 6,
      borderSkipped: false
    });
    charts[canvasId] = new Chart(ctx, { type: 'bar', data: { labels: labels, datasets: datasets }, options: options });
  }

  // ── Loading helpers ────────────────────────────────────────────────────────
  function showLoading(widgetId) {
    var el = document.getElementById('loading-' + widgetId);
    if (el) el.style.display = 'flex';
  }

  function hideLoading(widgetId) {
    var el = document.getElementById('loading-' + widgetId);
    if (el) el.style.display = 'none';
  }

  function setKpi(id, html) {
    var el = document.getElementById('kpi-' + id);
    if (el) el.innerHTML = html;
  }

  function kpiHtml(dot, label, value) {
    return '<div class="dash-kpi">' +
      '<span class="dash-kpi__dot" style="background:' + dot + '"></span>' +
      '<div><div class="dash-kpi__label">' + label + '</div>' +
      '<div class="dash-kpi__value">' + value + '</div></div></div>';
  }

  // ── Widget: Penjualan Harian ───────────────────────────────────────────────
  function loadPenjualan(days) {
    showLoading('penjualan');
    fetch('/dashboard/api/penjualan/?days=' + days + getEbParams())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('penjualan');
        setKpi('penjualan',
          kpiHtml(C.blue,  'Total Penjualan', fmtIDR(d.totals.nilai_penjualan)) +
          kpiHtml(C.green, 'Laba Kotor',      fmtIDR(d.totals.pendapatan_kotor))
        );

        var avg = d.series.nilai_penjualan.reduce(function(a,b){return a+b;},0) / (d.series.nilai_penjualan.length||1);

        renderLineChart('chart-penjualan', d.labels, [
          {
            label: 'Nilai Penjualan',
            data: d.series.nilai_penjualan,
            borderColor: C.blue,
            backgroundColor: 'rgba(0,84,166,0.07)',
            fill: true
          },
          {
            label: 'Laba Kotor',
            data: d.series.pendapatan_kotor,
            borderColor: C.green,
            backgroundColor: 'rgba(16,185,129,0.07)',
            fill: true
          }
        ], {
          tooltipHandler: makeTooltipHandler(function(rows) {
            var nilai = (rows[0] && rows[0].raw) || 0;
            var kotor = (rows[1] && rows[1].raw) || 0;
            var margin = nilai > 0 ? Math.round(kotor/nilai*100) : 0;
            var vsAvg = avg > 0 ? Math.round((nilai-avg)/avg*100) : 0;
            var sign = vsAvg >= 0 ? '+' : '';
            return (margin > 0 ? 'Margin: ' + margin + '%' : '') +
              (vsAvg !== 0 ? (margin>0?'  •  ':'') + sign + vsAvg + '% dari rata-rata' : '');
          })
        });
      })
      .catch(function() { hideLoading('penjualan'); });
  }

  // ── Widget: Profit Harian ─────────────────────────────────────────────────
  function loadProfit(days) {
    showLoading('profit');
    fetch('/dashboard/api/profit/?days=' + days + getEbParams())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('profit');
        setKpi('profit',
          kpiHtml(C.green, 'Total Laba', fmtIDR(d.totals.total_profit)) +
          kpiHtml(C.amber, 'Margin Rata-rata', d.totals.avg_margin + '%')
        );
        renderBarChart('chart-profit', d.labels, [
          {
            label: 'Laba (IDR)',
            data: d.series.profit,
            backgroundColor: 'rgba(16,185,129,0.75)',
            borderColor: C.green,
            borderWidth: 1.5
          }
        ], {
          tooltipHandler: makeTooltipHandler(function(rows) {
            var profit = (rows[0] && rows[0].raw) || 0;
            var idx = rows[0] && rows[0].dataIndex;
            var margin = (d.series.margin && d.series.margin[idx]) || 0;
            return profit > 0 ? 'Margin: ' + margin + '%' : 'Tidak ada penjualan';
          })
        });
      })
      .catch(function() { hideLoading('profit'); });
  }

  // ── Widget: Pengeluaran Kas ───────────────────────────────────────────────
  function loadPengeluaran(days) {
    showLoading('pengeluaran');
    fetch('/dashboard/api/pengeluaran/?days=' + days + getEbParams())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('pengeluaran');
        setKpi('pengeluaran',
          kpiHtml(C.red,   'Total Keluar', fmtIDR(d.totals.total)) +
          kpiHtml(C.amber, 'Rata-rata/Hari', fmtIDR(d.totals.avg_harian))
        );

        var max = Math.max.apply(null, d.series);
        renderBarChart('chart-pengeluaran', d.labels, [
          {
            label: 'Keluar Kas/Bank',
            data: d.series,
            backgroundColor: d.series.map(function(v) {
              return v === max && max > 0 ? 'rgba(239,68,68,0.85)' : 'rgba(239,68,68,0.45)';
            }),
            borderColor: C.red,
            borderWidth: 1.5
          }
        ], {
          tooltipHandler: makeTooltipHandler(function(rows) {
            var v = (rows[0] && rows[0].raw) || 0;
            if (v === 0) return 'Tidak ada pengeluaran kas';
            var vsAvg = d.totals.avg_harian > 0 ? Math.round((v - d.totals.avg_harian) / d.totals.avg_harian * 100) : 0;
            var sign = vsAvg >= 0 ? '+' : '';
            return sign + vsAvg + '% dari rata-rata harian';
          })
        });
      })
      .catch(function() { hideLoading('pengeluaran'); });
  }

  // ── Widget: Rata-rata Pengeluaran ─────────────────────────────────────────
  function loadRataPengeluaran(days) {
    showLoading('rata-pengeluaran');
    fetch('/dashboard/api/rata-pengeluaran/?days=' + days + getEbParams())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('rata-pengeluaran');
        document.getElementById('stat-avg').textContent   = fmtIDR(d.avg_harian);
        document.getElementById('stat-total').textContent  = fmtIDR(d.total);
        document.getElementById('stat-max').textContent    = fmtIDR(d.max_harian);
        document.getElementById('stat-aktif').textContent  = d.hari_aktif + ' hari';
        document.getElementById('stat-days-label').textContent = 'dari ' + d.days + ' hari';
      })
      .catch(function() { hideLoading('rata-pengeluaran'); });
  }

  // ── Widget: Top 5 Persediaan ──────────────────────────────────────────────
  function loadTopPersediaan(days) {
    showLoading('top-persediaan');
    fetch('/dashboard/api/top-persediaan/?days=' + days + getEbParams())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('top-persediaan');
        if (!d.items || d.items.length === 0) {
          document.getElementById('chart-top-persediaan-wrap').innerHTML =
            '<div class="dash-empty"><div class="dash-empty__icon">📦</div>' +
            '<p class="dash-empty__text">Belum ada penjualan di periode ini</p>' +
            '<p class="dash-empty__sub">Coba pilih range yang lebih panjang</p></div>';
          return;
        }

        var maxQty = Math.max.apply(null, d.items.map(function(i){return i.total_qty;}));

        renderBarChart('chart-top-persediaan', d.items.map(function(i){
          return i.nama.length > 20 ? i.nama.substring(0,20)+'…' : i.nama;
        }), [
          {
            label: 'Qty Terjual',
            data: d.items.map(function(i){return i.total_qty;}),
            backgroundColor: d.items.map(function(i,idx){
              return i.total_qty === maxQty ? 'rgba(0,84,166,0.85)' : C.multi[idx % C.multi.length] + '66';
            }),
            borderColor: d.items.map(function(i,idx){return C.multi[idx % C.multi.length];}),
            borderWidth: 1.5
          }
        ], {
          horizontal: true,
          tooltipHandler: makeTooltipHandler(function(rows) {
            var idx = rows[0] && rows[0].dataIndex;
            var item = d.items[idx];
            if (!item) return '';
            return fmtIDR(item.total_nilai) + ' • ' + item.jumlah_transaksi + ' transaksi';
          }),
          xCallback: function(v) { return fmtNum(v); }
        });
      })
      .catch(function() { hideLoading('top-persediaan'); });
  }

  // ── Widget: Saldo Persediaan (tabel) ─────────────────────────────────────
  function loadSaldoPersediaan() {
    showLoading('saldo');
    fetch('/dashboard/api/saldo-persediaan/' + getEbParams().replace('&','?'))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('saldo');
        var tbody = document.getElementById('saldo-tbody');
        if (!tbody) return;

        if (!d.rows || d.rows.length === 0) {
          tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:24px;color:var(--ni-text-muted);">' +
            '<span style="font-size:1.5rem;display:block;margin-bottom:6px;">🏷️</span>' +
            'Belum ada item ditandai — klik <strong>Tandai Item</strong> untuk mulai</td></tr>';
        } else {
          tbody.innerHTML = d.rows.map(function(row) {
            return '<tr>' +
              '<td><div style="font-weight:500;font-size:0.8125rem;">' + row.nama + '</div>' +
              '<div style="font-size:0.6875rem;color:var(--ni-text-muted);">' + row.item_id + '</div></td>' +
              '<td class="dash-utang-amount" style="text-align:right;">' + fmtIDR(row.nilai) + '</td>' +
              '<td style="text-align:right;font-size:0.8125rem;">' + fmtNum(row.qty) + '</td>' +
              '</tr>';
          }).join('');
        }
        if (tagPanelOpen) loadTagPanel();
      })
      .catch(function() { hideLoading('saldo'); });
  }

  // ── Widget: Recent Sales ─────────────────────────────────────────────────
  var recentSalesPage = 1;
  var recentSalesDays = 7;

  function loadRecentSales(days, page) {
    recentSalesDays = days || recentSalesDays;
    recentSalesPage = page || 1;
    showLoading('recent-sales');
    fetch('/dashboard/api/recent-sales/?days=' + recentSalesDays + '&page=' + recentSalesPage + getEbParams())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('recent-sales');
        var tbody = document.getElementById('recent-sales-tbody');
        var infoEl = document.getElementById('recent-sales-info');
        if (!tbody) return;

        if (!d.rows || d.rows.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--ni-text-muted);">' +
            '<span style="font-size:1.5rem;display:block;margin-bottom:6px;">🛒</span>' +
            'Belum ada penjualan di periode ini</td></tr>';
        } else {
          tbody.innerHTML = d.rows.map(function (row) {
            var profitClass = row.profit < 0 ? ' dash-utang-amount--danger' : '';
            return '<tr>' +
              '<td style="white-space:nowrap;color:var(--ni-text-muted);font-size:0.75rem;">' + row.tanggal + '</td>' +
              '<td><div style="font-weight:500;font-size:0.8125rem;">' + row.item + '</div>' +
              '<div style="font-size:0.6875rem;color:var(--ni-text-muted);">' + row.item_id + '</div></td>' +
              '<td style="font-size:0.75rem;color:var(--ni-text-muted);max-width:140px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + row.entitas_bisnis + '</td>' +
              '<td style="text-align:right;font-size:0.8125rem;">' + fmtNum(row.qty) + '</td>' +
              '<td class="dash-utang-amount" style="text-align:right;">' + fmtIDR(row.total) + '</td>' +
              '<td style="text-align:right;color:var(--ni-text-muted);font-size:0.8125rem;">' + fmtIDR(row.hpp) + '</td>' +
              '<td class="dash-utang-amount' + profitClass + '" style="text-align:right;font-weight:700;">' + fmtIDR(row.profit) + '</td>' +
              '</tr>';
          }).join('');
        }

        var p = d.pagination;
        if (infoEl) {
          infoEl.textContent = p.total > 0
            ? 'Menampilkan ' + Math.min((p.page-1)*10+1, p.total) + '–' + Math.min(p.page*10, p.total) + ' dari ' + p.total + ' item'
            : '';
        }
        var prev = document.getElementById('recent-sales-prev');
        var next = document.getElementById('recent-sales-next');
        if (prev) prev.disabled = p.page <= 1;
        if (next) next.disabled = p.page >= p.total_pages;
        if (typeof lucide !== 'undefined') lucide.createIcons();
      })
      .catch(function () { hideLoading('recent-sales'); });
  }

  // ── Widget: Utang Jatuh Tempo ─────────────────────────────────────────────
  var utangPage = 1;

  function loadUtang(page) {
    utangPage = page;
    showLoading('utang');
    fetch('/dashboard/api/utang/?page=' + page + getEbParams())
      .then(function (r) { return r.json(); })
      .then(function (d) {
        hideLoading('utang');
        var tbody = document.getElementById('utang-tbody');
        var paginationEl = document.getElementById('utang-pagination');
        var infoEl = document.getElementById('utang-info');

        if (!tbody) return;

        if (d.rows.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--ni-text-muted);">' +
            '<span style="font-size:1.5rem;display:block;margin-bottom:6px;">✅</span>' +
            'Tidak ada utang yang jatuh tempo — bagus!</td></tr>';
        } else {
          tbody.innerHTML = d.rows.map(function(row) {
            var badge;
            if (row.is_overdue) {
              badge = '<span class="dash-utang-badge dash-utang-badge--overdue">' +
                '<i data-lucide="alert-circle" style="width:10px;height:10px"></i> ' +
                Math.abs(row.days_to_due) + ' hari lalu</span>';
            } else if (row.due_soon) {
              badge = '<span class="dash-utang-badge dash-utang-badge--due-soon">' +
                '<i data-lucide="clock" style="width:10px;height:10px"></i> ' +
                (row.days_to_due === 0 ? 'Hari ini' : row.days_to_due + ' hari lagi') + '</span>';
            } else {
              badge = '<span class="dash-utang-badge dash-utang-badge--open">' + row.tanggal_jatuh_tempo + '</span>';
            }

            var outstandingClass = row.is_overdue ? ' dash-utang-amount--danger' : '';
            return '<tr>' +
              '<td style="font-weight:600;font-size:0.8125rem;">' + row.nomor_utang + '</td>' +
              '<td style="max-width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + row.kreditor + '</td>' +
              '<td>' + badge + '</td>' +
              '<td class="dash-utang-amount" style="text-align:right;">' + fmtIDR(row.total_amount) + '</td>' +
              '<td class="dash-utang-amount' + outstandingClass + '" style="text-align:right;">' + fmtIDR(row.outstanding) + '</td>' +
              '<td style="text-align:right;"><a href="/utang/' + row.id + '/" class="ni-btn ni-btn--primary ni-btn--sm" style="font-size:0.6875rem;padding:3px 8px;">Bayar</a></td>' +
              '</tr>';
          }).join('');
        }

        // Pagination
        var p = d.pagination;
        if (infoEl) {
          infoEl.textContent = 'Menampilkan ' + Math.min((p.page-1)*10+1, p.total) + '–' +
            Math.min(p.page*10, p.total) + ' dari ' + p.total + ' utang';
        }

        var prevBtn = document.getElementById('utang-prev');
        var nextBtn = document.getElementById('utang-next');
        if (prevBtn) prevBtn.disabled = p.page <= 1;
        if (nextBtn) nextBtn.disabled = p.page >= p.total_pages;

        if (typeof lucide !== 'undefined') lucide.createIcons();
      })
      .catch(function() { hideLoading('utang'); });
  }

  // ── Tag panel (checkbox + batch Simpan) ──────────────────────────────────
  var tagPanelOpen = false;
  var tagSearchTimeout = null;

  function loadTagPanel(query) {
    var eb = getEbParams().replace('&', '?');
    var url = '/dashboard/api/tag-item/' + eb + (query ? (eb ? '&' : '?') + 'q=' + encodeURIComponent(query) : '');
    fetch(url)
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var list = document.getElementById('tag-list');
        if (!list) return;

        if (!d.items || d.items.length === 0) {
          list.innerHTML = '<div style="padding:16px;text-align:center;color:var(--ni-text-muted);font-size:0.8125rem;">Tidak ada item ditemukan</div>';
          return;
        }

        list.innerHTML = d.items.map(function(item) {
          var checked = item.tagged ? ' checked' : '';
          var taggedClass = item.tagged ? ' dash-tag-item--tagged' : '';
          return '<label class="dash-tag-item' + taggedClass + '">' +
            '<input type="checkbox" data-item-id="' + item.id + '"' + checked + ' style="display:none;">' +
            '<span class="dash-tag-item__check">' +
            (item.tagged ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="width:10px;height:10px"><polyline points="20 6 9 17 4 12"/></svg>' : '') +
            '</span>' +
            '<span class="dash-tag-item__name">' + item.nama + '</span>' +
            '<span class="dash-tag-item__id">' + item.item_id + '</span>' +
            '</label>';
        }).join('');

        // Toggle visual state on label click (no AJAX)
        list.querySelectorAll('.dash-tag-item').forEach(function(el) {
          el.addEventListener('click', function(e) {
            if (e.target.tagName === 'INPUT') return; // handled by checkbox
            var cb = el.querySelector('input[type=checkbox]');
            if (!cb) return;
            cb.checked = !cb.checked;
            if (cb.checked) {
              el.classList.add('dash-tag-item--tagged');
              el.querySelector('.dash-tag-item__check').innerHTML =
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="width:10px;height:10px"><polyline points="20 6 9 17 4 12"/></svg>';
            } else {
              el.classList.remove('dash-tag-item--tagged');
              el.querySelector('.dash-tag-item__check').innerHTML = '';
            }
          });
        });
      });
  }

  function saveTags() {
    var list = document.getElementById('tag-list');
    if (!list) return;
    var checked = list.querySelectorAll('input[type=checkbox]:checked');
    var ids = [];
    checked.forEach(function(cb) { ids.push(parseInt(cb.dataset.itemId)); });

    var btn = document.getElementById('tag-save-btn');
    if (btn) btn.disabled = true;

    var ebParams = getEbParams();
    var ebId = null;
    var m = ebParams.match(/eb_id=(\d+)/);
    if (m) ebId = parseInt(m[1]);
    fetch('/dashboard/api/tag-item/', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify({action: 'save_all', item_ids: ids, eb_id: ebId})
    })
      .then(function(r) { return r.json(); })
      .then(function() {
        if (btn) btn.disabled = false;
        loadSaldoPersediaan();
      })
      .catch(function() { if (btn) btn.disabled = false; });
  }

  function toggleTagPanel() {
    tagPanelOpen = !tagPanelOpen;
    var panel = document.getElementById('tag-panel-body');
    var btn = document.getElementById('tag-panel-toggle');
    if (!panel) return;
    if (tagPanelOpen) {
      panel.style.display = 'block';
      if (btn) {
        btn.innerHTML = '<i data-lucide="chevron-up" style="width:14px;height:14px"></i> Sembunyikan';
        if (typeof lucide !== 'undefined') lucide.createIcons();
      }
      loadTagPanel();
    } else {
      panel.style.display = 'none';
      if (btn) {
        btn.innerHTML = '<i data-lucide="tag" style="width:14px;height:14px"></i> Tandai Item';
        if (typeof lucide !== 'undefined') lucide.createIcons();
      }
    }
  }

  // ── CSRF ──────────────────────────────────────────────────────────────────
  function getCsrf() {
    var meta = document.querySelector('[name=csrfmiddlewaretoken]');
    if (meta) return meta.value;
    var cookie = document.cookie.split(';').find(function(c){return c.trim().startsWith('csrftoken=');});
    return cookie ? cookie.split('=')[1].trim() : '';
  }

  // ── Greeting & date ───────────────────────────────────────────────────────
  function setGreeting() {
    var h = new Date().getHours();
    var greet = h < 12 ? 'Selamat Pagi' : h < 15 ? 'Selamat Siang' : h < 18 ? 'Selamat Sore' : 'Selamat Malam';
    var el = document.getElementById('dash-greeting');
    if (el) el.textContent = greet + ' 👋';

    var dateEl = document.getElementById('dash-date');
    if (dateEl) {
      var now = new Date();
      var days = ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'];
      var months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ags','Sep','Okt','Nov','Des'];
      dateEl.textContent = days[now.getDay()] + ', ' + now.getDate() + ' ' + months[now.getMonth()] + ' ' + now.getFullYear();
    }
  }

  // ── Chip switcher binding ─────────────────────────────────────────────────
  function bindChips() {
    document.querySelectorAll('.ni-chart-periods[data-widget]').forEach(function(container) {
      container.addEventListener('click', function(e) {
        var btn = e.target.closest('.ni-chart-period');
        if (!btn) return;
        var days = parseInt(btn.dataset.days);
        var widget = container.dataset.widget;
        container.querySelectorAll('.ni-chart-period').forEach(function(b) {
          b.classList.remove('ni-chart-period--active');
        });
        btn.classList.add('ni-chart-period--active');

        switch (widget) {
          case 'penjualan':       loadPenjualan(days);       break;
          case 'profit':          loadProfit(days);           break;
          case 'pengeluaran':     loadPengeluaran(days);      break;
          case 'rata-pengeluaran':loadRataPengeluaran(days);  break;
          case 'top-persediaan':  loadTopPersediaan(days);    break;
          case 'saldo':           loadSaldoPersediaan(); break;
          case 'recent-sales':    loadRecentSales(days, 1); break;
        }
      });
    });
  }

  // bindSaldoTabs removed — no chart tabs needed

  // ── Utang pagination ──────────────────────────────────────────────────────
  function bindUtangPagination() {
    var prev = document.getElementById('utang-prev');
    var next = document.getElementById('utang-next');
    if (prev) prev.addEventListener('click', function() { if (utangPage > 1) loadUtang(utangPage - 1); });
    if (next) next.addEventListener('click', function() { loadUtang(utangPage + 1); });
  }

  // ── Recent Sales pagination ───────────────────────────────────────────────
  function bindRecentSalesPagination() {
    var prev = document.getElementById('recent-sales-prev');
    var next = document.getElementById('recent-sales-next');
    if (prev) prev.addEventListener('click', function() { if (recentSalesPage > 1) loadRecentSales(recentSalesDays, recentSalesPage - 1); });
    if (next) next.addEventListener('click', function() { loadRecentSales(recentSalesDays, recentSalesPage + 1); });
  }

  // ── Tag panel toggle + save ───────────────────────────────────────────────
  function bindTagPanel() {
    var btn = document.getElementById('tag-panel-toggle');
    if (btn) btn.addEventListener('click', toggleTagPanel);

    var saveBtn = document.getElementById('tag-save-btn');
    if (saveBtn) saveBtn.addEventListener('click', saveTags);

    var searchInput = document.getElementById('tag-search');
    if (searchInput) {
      searchInput.addEventListener('input', function() {
        clearTimeout(tagSearchTimeout);
        tagSearchTimeout = setTimeout(function() {
          loadTagPanel(searchInput.value);
        }, 300);
      });
    }
  }

  // ── EB selector ───────────────────────────────────────────────────────────
  function showEbUpdating(show) {
    var el = document.getElementById('eb-updating');
    if (el) el.style.display = show ? 'flex' : 'none';
  }

  function reloadAllWidgets() {
    var daysRS = getActiveDays('recent-sales') || 7;
    var days7  = getActiveDays('penjualan') || 7;
    var days7p = getActiveDays('profit')    || 7;
    var days7e = getActiveDays('pengeluaran') || 7;
    var days30r = getActiveDays('rata-pengeluaran') || 30;
    var days30t = getActiveDays('top-persediaan')   || 30;
    loadRecentSales(daysRS, 1);
    loadPenjualan(days7);
    loadProfit(days7p);
    loadPengeluaran(days7e);
    loadRataPengeluaran(days30r);
    loadTopPersediaan(days30t);
    loadSaldoPersediaan();
    loadUtang(1);
  }

  function getActiveDays(widget) {
    var container = document.querySelector('.ni-chart-periods[data-widget="' + widget + '"]');
    if (!container) return null;
    var btn = container.querySelector('.ni-chart-period--active');
    return btn ? parseInt(btn.dataset.days) : null;
  }

  function setEbSession(ebId, lv2Id, lv3Id, onDone) {
    fetch('/dashboard/api/set-eb/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({ eb_id: ebId, eb_lv2_id: lv2Id, eb_lv3_id: lv3Id })
    })
      .then(function (r) { return r.json(); })
      .then(function () { if (onDone) onDone(); })
      .catch(function () { if (onDone) onDone(); });
  }

  function loadLv2Options(ebId, selectedLv2, callback) {
    fetch('/dashboard/api/eb-options/?eb_id=' + ebId)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var wrap = document.getElementById('lv2-wrap');
        var sel  = document.getElementById('eb-select-lv2');
        if (!wrap || !sel || !d.lv2) return;
        if (d.lv2.length === 0) {
          wrap.style.display = 'none';
          return;
        }
        sel.innerHTML = '<option value="">— Semua Cabang —</option>' +
          d.lv2.map(function (o) {
            return '<option value="' + o.id + '"' + (o.id === selectedLv2 ? ' selected' : '') + '>' + o.nama + '</option>';
          }).join('');
        wrap.style.display = '';
        if (typeof lucide !== 'undefined') lucide.createIcons();
        if (callback) callback();
      });
  }

  function loadLv3Options(lv2Id, selectedLv3) {
    fetch('/dashboard/api/eb-options/?eb_lv2_id=' + lv2Id)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var wrap = document.getElementById('lv3-wrap');
        var sel  = document.getElementById('eb-select-lv3');
        if (!wrap || !sel || !d.lv3) return;
        if (d.lv3.length === 0) {
          wrap.style.display = 'none';
          return;
        }
        sel.innerHTML = '<option value="">— Semua Sub-cabang —</option>' +
          d.lv3.map(function (o) {
            return '<option value="' + o.id + '"' + (o.id === selectedLv3 ? ' selected' : '') + '>' + o.nama + '</option>';
          }).join('');
        wrap.style.display = '';
        if (typeof lucide !== 'undefined') lucide.createIcons();
      });
  }

  function bindEbSelector() {
    var lv1 = document.getElementById('eb-select-lv1');
    var lv2 = document.getElementById('eb-select-lv2');
    var lv3 = document.getElementById('eb-select-lv3');

    if (lv1) {
      lv1.addEventListener('change', function () {
        var ebId = parseInt(lv1.value) || null;
        ebState.eb_id     = ebId;
        ebState.eb_lv2_id = null;
        ebState.eb_lv3_id = null;

        // Hide Lv2/Lv3 until loaded
        var lv2wrap = document.getElementById('lv2-wrap');
        var lv3wrap = document.getElementById('lv3-wrap');
        if (lv2wrap) lv2wrap.style.display = 'none';
        if (lv3wrap) lv3wrap.style.display = 'none';

        showEbUpdating(true);
        setEbSession(ebId, null, null, function () {
          loadLv2Options(ebId, null, null);
          reloadAllWidgets();
          showEbUpdating(false);
        });
      });
    }

    if (lv2) {
      lv2.addEventListener('change', function () {
        var lv2Id = parseInt(lv2.value) || null;
        ebState.eb_lv2_id = lv2Id;
        ebState.eb_lv3_id = null;

        var lv3wrap = document.getElementById('lv3-wrap');
        if (lv3wrap) lv3wrap.style.display = 'none';

        showEbUpdating(true);
        setEbSession(ebState.eb_id, lv2Id, null, function () {
          if (lv2Id) loadLv3Options(lv2Id, null);
          reloadAllWidgets();
          showEbUpdating(false);
        });
      });
    }

    if (lv3) {
      lv3.addEventListener('change', function () {
        var lv3Id = parseInt(lv3.value) || null;
        ebState.eb_lv3_id = lv3Id;
        showEbUpdating(true);
        setEbSession(ebState.eb_id, ebState.eb_lv2_id, lv3Id, function () {
          reloadAllWidgets();
          showEbUpdating(false);
        });
      });
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    initEbState();
    setGreeting();
    bindChips();
    bindUtangPagination();
    bindTagPanel();
    bindEbSelector();
    bindRecentSalesPagination();

    // Initial loads — EB params already in ebState from initEbState()
    loadRecentSales(7, 1);
    loadPenjualan(7);
    loadProfit(7);
    loadPengeluaran(7);
    loadRataPengeluaran(30);
    loadTopPersediaan(30);
    loadSaldoPersediaan();
    loadUtang(1);
  });

  // ── Expose for inventory list tag toggle ─────────────────────────────────
  window.niDashTagToggle = function(itemId, btn) {
    fetch('/dashboard/api/tag-item/', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify({item_id: parseInt(itemId)})
    })
      .then(function(r) { return r.json(); })
      .then(function(res) {
        var isTagged = res.status === 'tagged';
        if (isTagged) {
          btn.classList.add('dash-tag-btn--active');
          btn.title = 'Di-pantau di Dashboard — klik untuk batalkan';
          btn.querySelector('span').textContent = 'Di Dashboard';
        } else {
          btn.classList.remove('dash-tag-btn--active');
          btn.title = 'Pantau di Dashboard';
          btn.querySelector('span').textContent = 'Pantau';
        }
      });
  };

}());
