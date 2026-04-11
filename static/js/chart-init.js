/**
 * Naveda Integra — chart-init.js
 * Chart.js initialization helpers for the dashboard.
 * Include Chart.js CDN before this file, then call niCharts.line() / niCharts.doughnut().
 */
var niCharts = (function () {
  'use strict';

  var COLORS = {
    primary: '#0054a6',
    accent: '#6366f1',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    info: '#06b6d4',
    muted: '#94a3b8',
    border: '#e2e8f0',
    bg: '#f8fafc'
  };

  var defaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          usePointStyle: true,
          padding: 20,
          font: { family: "'Inter', sans-serif", size: 12 }
        }
      },
      tooltip: {
        backgroundColor: '#1e293b',
        titleFont: { family: "'Inter', sans-serif", size: 13 },
        bodyFont: { family: "'Inter', sans-serif", size: 12 },
        padding: 12,
        cornerRadius: 8,
        boxPadding: 4
      }
    }
  };

  function line(canvasId, labels, datasets) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: Object.assign({}, defaults, {
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { family: "'Inter', sans-serif", size: 11 } }
          },
          y: {
            beginAtZero: true,
            grid: { color: COLORS.border },
            ticks: { font: { family: "'Inter', sans-serif", size: 11 } }
          }
        },
        elements: {
          line: { tension: 0.3, borderWidth: 2.5 },
          point: { radius: 3, hoverRadius: 6 }
        }
      })
    });
  }

  function doughnut(canvasId, labels, data, colors) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: colors || [COLORS.primary, COLORS.accent, COLORS.success, COLORS.warning, COLORS.danger, COLORS.info],
          borderWidth: 0,
          hoverOffset: 6
        }]
      },
      options: Object.assign({}, defaults, {
        cutout: '70%'
      })
    });
  }

  function bar(canvasId, labels, datasets) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: 'bar',
      data: { labels: labels, datasets: datasets },
      options: Object.assign({}, defaults, {
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { family: "'Inter', sans-serif", size: 11 } }
          },
          y: {
            beginAtZero: true,
            grid: { color: COLORS.border },
            ticks: { font: { family: "'Inter', sans-serif", size: 11 } }
          }
        },
        borderRadius: 6,
        borderSkipped: false
      })
    });
  }

  return { line: line, doughnut: doughnut, bar: bar, COLORS: COLORS };
})();
