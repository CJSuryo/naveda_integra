(function () {
  'use strict';

  function initEbFilterModal() {
    var trigger = document.querySelector('.ni-eb-filter-trigger');
    if (!trigger) return;

    var modalId  = trigger.getAttribute('data-modal-id')  || 'ebFilterBackdrop';
    var inputsId = trigger.getAttribute('data-inputs-id') || 'ebHiddenInputs';
    var formId   = trigger.getAttribute('data-form-id')   || 'ebFilterForm';

    var backdrop  = document.getElementById(modalId);
    var inputs    = document.getElementById(inputsId);
    var form      = document.getElementById(formId);

    if (!backdrop) return;

    // Move backdrop to <body> so position:fixed isn't trapped by ancestor stacking contexts
    document.body.appendChild(backdrop);

    var search    = document.getElementById('ebFilterSearch');
    var tree      = document.getElementById('ebFilterTree');
    var emptyMsg  = document.getElementById('ebFilterEmpty');
    var clearBtn  = document.getElementById('ebFilterClear');
    var applyBtn  = document.getElementById('ebFilterApply');

    // ── Open / close ──────────────────────────────────────────────────────
    function openModal() {
      backdrop.classList.add('ni-modal-backdrop--visible');
      document.body.style.overflow = 'hidden';
      if (search) { search.value = ''; runSearch(''); }
      // Auto-expand nodes that have checked descendants
      expandCheckedAncestors();
      if (search) search.focus();
    }

    function closeModal() {
      backdrop.classList.remove('ni-modal-backdrop--visible');
      document.body.style.overflow = '';
    }

    trigger.addEventListener('click', openModal);

    backdrop.querySelectorAll('[data-eb-modal-close]').forEach(function (el) {
      el.addEventListener('click', closeModal);
    });

    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) closeModal();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && backdrop.classList.contains('ni-modal-backdrop--visible')) {
        closeModal();
      }
    });

    // ── Row expand / collapse ─────────────────────────────────────────────
    backdrop.querySelectorAll('.ni-eb-filter-row--has-children').forEach(function (row) {
      row.addEventListener('click', function (e) {
        // Ignore clicks originating from the checkbox cell
        if (e.target.closest('.ni-eb-filter-cb-cell')) return;
        toggleChildren(row);
      });
    });

    function toggleChildren(row) {
      var childrenId = row.getAttribute('data-children-id');
      if (!childrenId) return;
      var children = document.getElementById(childrenId);
      var arrow    = row.querySelector('.ni-eb-filter-arrow');
      if (!children) return;
      var open = children.classList.contains('ni-eb-filter-children--open');
      children.classList.toggle('ni-eb-filter-children--open', !open);
      if (arrow) arrow.classList.toggle('ni-eb-filter-arrow--open', !open);
    }

    function openChildren(row) {
      var childrenId = row.getAttribute('data-children-id');
      if (!childrenId) return;
      var children = document.getElementById(childrenId);
      var arrow    = row.querySelector('.ni-eb-filter-arrow');
      if (!children) return;
      children.classList.add('ni-eb-filter-children--open');
      if (arrow) arrow.classList.add('ni-eb-filter-arrow--open');
    }

    function expandCheckedAncestors() {
      // For every checked checkbox, walk up and open parent children containers
      backdrop.querySelectorAll('.ni-eb-filter-cb:checked').forEach(function (cb) {
        var node = cb.closest('.ni-eb-filter-node');
        if (!node) return;
        var parent = node.parentElement;
        while (parent && parent !== tree) {
          if (parent.classList.contains('ni-eb-filter-children')) {
            parent.classList.add('ni-eb-filter-children--open');
            // Also rotate the arrow on the parent row
            var parentRow = parent.previousElementSibling;
            if (parentRow) {
              var arrow = parentRow.querySelector('.ni-eb-filter-arrow');
              if (arrow) arrow.classList.add('ni-eb-filter-arrow--open');
            }
          }
          parent = parent.parentElement;
        }
      });
    }

    // ── Search ────────────────────────────────────────────────────────────
    if (search) {
      search.addEventListener('input', function () {
        runSearch(this.value.toLowerCase().trim());
      });
    }

    function runSearch(term) {
      var anyVisible = false;
      if (tree) {
        tree.querySelectorAll('.ni-eb-filter-node').forEach(function (node) {
          var name = (node.getAttribute('data-name') || '').toLowerCase();
          // Only top-level nodes have data-name; nested ones inherit parent visibility
          if (node.parentElement === tree || node.closest('.ni-eb-filter-node') === node) {
            var match = !term || name.indexOf(term) !== -1;
            // Also check children names
            if (!match && term) {
              var childNames = node.querySelectorAll('.ni-eb-filter-node');
              childNames.forEach(function (child) {
                if ((child.getAttribute('data-name') || '').indexOf(term) !== -1) match = true;
              });
            }
            node.style.display = match ? '' : 'none';
            if (match) anyVisible = true;
          }
        });
      }
      if (emptyMsg) emptyMsg.style.display = anyVisible || !term ? 'none' : 'block';
    }

    // ── Clear all ─────────────────────────────────────────────────────────
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        backdrop.querySelectorAll('.ni-eb-filter-cb').forEach(function (cb) {
          cb.checked = false;
        });
      });
    }

    // ── Apply ─────────────────────────────────────────────────────────────
    if (applyBtn) {
      applyBtn.addEventListener('click', function () {
        if (!inputs) return;
        inputs.innerHTML = '';
        backdrop.querySelectorAll('.ni-eb-filter-cb:checked').forEach(function (cb) {
          var inp = document.createElement('input');
          inp.type = 'hidden';
          inp.name = 'entitas_bisnis';
          inp.value = cb.value;
          inputs.appendChild(inp);
        });
        closeModal();
        var targetForm = form || (formId ? document.getElementById(formId) : null);
        if (targetForm) targetForm.submit();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEbFilterModal);
  } else {
    initEbFilterModal();
  }
})();
