(function () {
  'use strict';

  /**
   * Handle paste events on number inputs.
   * Converts pasted values like "1,700,000" or "1.700.000" to "1700000".
   * Detects whether commas/dots are thousands separators vs decimal points.
   */
  document.addEventListener('paste', function (e) {
    var target = e.target;
    if (!target || target.tagName !== 'INPUT') return;
    if (target.type !== 'number' && !target.classList.contains('ni-jm-input') &&
        !target.classList.contains('ni-purchase-input') &&
        !target.classList.contains('ni-sales-input') &&
        !target.classList.contains('ni-input')) return;
    if (target.type !== 'number') return;

    var pasted = (e.clipboardData || window.clipboardData).getData('text');
    if (!pasted) return;

    pasted = pasted.trim();

    // If it already looks like a plain number, let the browser handle it
    if (/^-?\d+(\.\d+)?$/.test(pasted)) return;

    e.preventDefault();

    // Detect format:
    // "1,700,000" or "1,700,000.50" → commas are thousands
    // "1.700.000" or "1.700.000,50" → dots are thousands, comma is decimal
    // "1700000,50" → comma is decimal
    var cleaned = pasted;

    // Count commas and dots
    var commaCount = (pasted.match(/,/g) || []).length;
    var dotCount = (pasted.match(/\./g) || []).length;

    if (commaCount > 1) {
      // Multiple commas = commas are thousands separators (e.g. "1,700,000")
      cleaned = pasted.replace(/,/g, '');
    } else if (dotCount > 1) {
      // Multiple dots = dots are thousands separators (e.g. "1.700.000")
      cleaned = pasted.replace(/\./g, '');
      // If there's also a comma, it's the decimal separator
      cleaned = cleaned.replace(',', '.');
    } else if (commaCount === 1 && dotCount === 1) {
      // One of each: the last one is the decimal separator
      var commaPos = pasted.lastIndexOf(',');
      var dotPos = pasted.lastIndexOf('.');
      if (commaPos > dotPos) {
        // "1.700,50" → dot is thousands, comma is decimal
        cleaned = pasted.replace(/\./g, '').replace(',', '.');
      } else {
        // "1,700.50" → comma is thousands, dot is decimal
        cleaned = pasted.replace(/,/g, '');
      }
    } else if (commaCount === 1 && dotCount === 0) {
      // Single comma: check if it looks like thousands or decimal
      var parts = pasted.split(',');
      if (parts[1] && parts[1].length === 3 && /^\d+$/.test(parts[1])) {
        // "1,700" — ambiguous, but given context (Indonesian accounting), treat as thousands
        cleaned = pasted.replace(',', '');
      } else {
        // "1,5" or "100,50" — comma is decimal
        cleaned = pasted.replace(',', '.');
      }
    }

    // Remove any remaining non-numeric chars except dot and minus
    cleaned = cleaned.replace(/[^\d.\-]/g, '');

    // Set value and trigger input event
    target.value = cleaned;
    target.dispatchEvent(new Event('input', { bubbles: true }));
    target.dispatchEvent(new Event('change', { bubbles: true }));
  });
})();
