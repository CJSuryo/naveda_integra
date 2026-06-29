'use strict';

// Navbar scroll state
(function () {
  const nav = document.getElementById('lNav');
  if (!nav) return;
  const onScroll = () => nav.classList.toggle('is-scrolled', window.scrollY > 60);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// Mobile nav toggle
(function () {
  const toggle = document.getElementById('navToggle');
  const links = document.getElementById('navLinks');
  if (!toggle || !links) return;

  toggle.addEventListener('click', () => {
    const open = links.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', open);
  });

  links.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => {
      links.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
    });
  });
})();

// Tab switching
(function () {
  const buttons = document.querySelectorAll('.tab-btn');
  const panels = document.querySelectorAll('.tab-panel');
  if (!buttons.length) return;

  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      buttons.forEach(b => { b.classList.remove('is-active'); b.setAttribute('aria-selected', 'false'); });
      panels.forEach(p => p.classList.remove('is-active'));
      btn.classList.add('is-active');
      btn.setAttribute('aria-selected', 'true');
      const panel = document.getElementById('tab-' + btn.dataset.tab);
      if (!panel) return;
      panel.classList.add('is-active');
      panel.querySelectorAll('[data-reveal]').forEach(el => el.classList.add('is-visible'));
    });
  });
})();

// Scroll reveal via IntersectionObserver
(function () {
  const els = document.querySelectorAll('[data-reveal]');
  if (!els.length || !('IntersectionObserver' in window)) {
    els.forEach(el => el.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

  els.forEach(el => observer.observe(el));
})();

// Hero scroll cue
(function () {
  const cue = document.getElementById('scrollCue');
  const target = document.getElementById('problem');
  if (!cue || !target) return;
  cue.addEventListener('click', () => target.scrollIntoView({ behavior: 'smooth' }));
})();

// FAQ accordion
(function () {
  document.querySelectorAll('.l-faq__btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const row = btn.closest('.l-faq__row');
      const wasOpen = row.classList.contains('is-open');
      document.querySelectorAll('.l-faq__row.is-open').forEach(r => {
        r.classList.remove('is-open');
        r.querySelector('.l-faq__btn').setAttribute('aria-expanded', 'false');
      });
      if (!wasOpen) {
        row.classList.add('is-open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });
})();

// Contact form — WhatsApp submit + email fallback
(function () {
  const form = document.getElementById('contactForm');
  const emailBtn = document.getElementById('cfEmail');
  if (!form) return;

  function buildMessage() {
    const nama = document.getElementById('cfNama').value.trim();
    const org = document.getElementById('cfOrg').value.trim();
    const segment = document.getElementById('cfSegment').value;
    const pesan = document.getElementById('cfPesan').value.trim();
    const parts = ['Halo Naveda Integra Finance,'];
    if (nama) parts.push('Nama: ' + nama);
    if (org) parts.push('Bisnis/Organisasi: ' + org);
    if (segment) parts.push('Saya seorang: ' + segment);
    if (pesan) parts.push('\n' + pesan);
    return parts.join('\n');
  }

  form.addEventListener('submit', e => {
    e.preventDefault();
    const msg = buildMessage();
    window.open('https://wa.me/6285933570605?text=' + encodeURIComponent(msg), '_blank', 'noopener,noreferrer');
  });

  if (emailBtn) {
    emailBtn.addEventListener('click', () => {
      const nama = document.getElementById('cfNama').value.trim();
      const subject = 'Konsultasi Naveda Integra Finance' + (nama ? ' — ' + nama : '');
      const body = buildMessage();
      window.location.href = 'mailto:dantadwipayanastan@gmail.com?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
    });
  }
})();
