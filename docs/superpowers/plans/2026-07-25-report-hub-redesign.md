# Redesain Hub Laporan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesain 3 halaman hub laporan (Keuangan, Persediaan, Aset) menjadi menarik, konsisten, dan mudah dipindai — gaya kartu "Gradient Hero", header berwarna per kategori, kartu dikelompokkan ke seksi berlabel. Murni template + CSS; tidak menyentuh view/URL/model/Python.

**Architecture:** Satu stylesheet bersama `static/css/report-hub.css` mendefinisikan kelas `.ni-rhub-*` dan tema per kategori via CSS variable pada modifier root (`.ni-rhub--keuangan/--persediaan/--aset`). Tiap template hub menulis markup memakai kelas itu dan dimuat stylesheet lewat `{% block extra_css %}`. Ikon memakai lucide (`data-lucide`), yang di-init global oleh `sidebar.js`.

**Tech Stack:** Django templates, CSS custom properties, lucide icons. Tidak ada JS baru.

**Catatan pengerjaan:** Ini pekerjaan UI statis, jadi verifikasi = (a) `python manage.py check` untuk memastikan template kompilasi & `{% url %}` valid saat render, dan (b) pemeriksaan visual manual di browser. Tidak ada unit test framework untuk template statis; jangan mengarang test palsu. Commit tiap task.

**Prasyarat terverifikasi (jangan diubah):**
- Nama URL sudah dicek ada: `jurnal:laporan_laba_rugi`, `jurnal:neraca`, `jurnal:laporan_perubahan_ekuitas`, `jurnal:neraca_saldo`, `jurnal:buku_besar`, `jurnal:analisis_keuangan`; `inventory:laporan_valuasi`, `inventory:laporan_hpp`, `inventory:stock_card`, `inventory:stock_ledger`, `inventory:laporan_velocity`, `inventory:laporan_persediaan`; `aset_tetap:laporan_register`, `aset_tetap:laporan_penyusutan`.
- Pola `{% load static %}` + `{% block extra_css %}<link ...>` sudah dipakai di `templates/home.html`.
- `sidebar.js` memanggil `lucide.createIcons()` global di tiap halaman.
- Token yang dipakai ada di `static/css/layout.css`: `--ni-radius-lg`, `--ni-shadow-sm`, `--ni-bg-card`, `--ni-border`, `--ni-text`, `--ni-text-muted`.

---

## File Structure

- **Create:** `static/css/report-hub.css` — seluruh gaya `.ni-rhub-*` + 3 tema.
- **Modify (rewrite isi block):** `templates/jurnal/laporan_keuangan_hub.html`
- **Modify (rewrite isi block):** `templates/inventory/laporan_hub.html`
- **Modify (rewrite isi block):** `templates/aset_tetap/laporan_aset_hub.html`

---

## Task 1: Stylesheet bersama `report-hub.css`

**Files:**
- Create: `static/css/report-hub.css`

- [ ] **Step 1: Buat file CSS dengan seluruh isi berikut (persis)**

```css
/* report-hub.css — halaman hub laporan bertema (.ni-rhub). Hanya dimuat di 3 hub. */

/* ── Tema per kategori (default = keuangan) ───────────────────────────── */
.ni-rhub{
  --rhub-c1:#0054a6; --rhub-c2:#3b82f6;
  --rhub-chip-bg:#e8f0fe; --rhub-chip-fg:#0054a6;
  --rhub-glow:rgba(0,84,166,.14); --rhub-shadow:rgba(0,84,166,.42);
}
.ni-rhub--keuangan{
  --rhub-c1:#0054a6; --rhub-c2:#3b82f6;
  --rhub-chip-bg:#e8f0fe; --rhub-chip-fg:#0054a6;
  --rhub-glow:rgba(0,84,166,.14); --rhub-shadow:rgba(0,84,166,.42);
}
.ni-rhub--persediaan{
  --rhub-c1:#0d9488; --rhub-c2:#10b981;
  --rhub-chip-bg:#ecfdf5; --rhub-chip-fg:#0d9488;
  --rhub-glow:rgba(16,185,129,.14); --rhub-shadow:rgba(13,148,136,.42);
}
.ni-rhub--aset{
  --rhub-c1:#6366f1; --rhub-c2:#8b5cf6;
  --rhub-chip-bg:#eef2ff; --rhub-chip-fg:#6366f1;
  --rhub-glow:rgba(99,102,241,.14); --rhub-shadow:rgba(99,102,241,.42);
}

/* ── Tombol kembali (breadcrumb) ──────────────────────────────────────── */
.ni-rhub__back{
  display:inline-flex; align-items:center; gap:6px; margin-bottom:14px;
  font-size:.8125rem; font-weight:600; color:var(--ni-text-muted,#64748b);
  background:none; border:none; cursor:pointer; padding:4px 0; text-decoration:none;
}
.ni-rhub__back:hover{ color:var(--rhub-c1); }
.ni-rhub__back svg{ width:16px; height:16px; }

/* ── Hero ─────────────────────────────────────────────────────────────── */
.ni-rhub__hero{
  position:relative; overflow:hidden;
  background:linear-gradient(120deg, var(--rhub-c1), var(--rhub-c2));
  border-radius:var(--ni-radius-lg,16px);
  padding:26px 28px; color:#fff;
  display:flex; align-items:center; gap:20px;
  box-shadow:0 12px 26px -14px var(--rhub-shadow);
}
.ni-rhub__hero-glow{
  position:absolute; right:-40px; top:-50px; width:220px; height:220px;
  background:radial-gradient(circle, rgba(255,255,255,.18), transparent 70%);
  pointer-events:none;
}
.ni-rhub__hero-icon{
  width:60px; height:60px; border-radius:16px; flex-shrink:0;
  background:rgba(255,255,255,.16); display:grid; place-items:center;
}
.ni-rhub__hero-icon svg{ width:30px; height:30px; }
.ni-rhub__hero-text{ min-width:0; }
.ni-rhub__hero-title{ margin:0; font-size:1.375rem; font-weight:700; letter-spacing:-.01em; color:#fff; }
.ni-rhub__hero-sub{ margin:4px 0 0; font-size:.85rem; opacity:.9; }
.ni-rhub__hero-count{ margin-left:auto; text-align:right; flex-shrink:0; }
.ni-rhub__hero-count b{ font-size:1.75rem; display:block; line-height:1; font-weight:700; }
.ni-rhub__hero-count span{ font-size:.6875rem; opacity:.85; text-transform:uppercase; letter-spacing:.06em; }

/* ── Label seksi ──────────────────────────────────────────────────────── */
.ni-rhub__section-label{ display:flex; align-items:center; gap:12px; margin:26px 2px 14px; }
.ni-rhub__section-label span{
  font-size:.75rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  color:var(--ni-text-muted,#64748b); white-space:nowrap;
}
.ni-rhub__section-label::after{ content:""; flex:1; height:1px; background:var(--ni-border,#e2e8f0); }

/* ── Grid ─────────────────────────────────────────────────────────────── */
.ni-rhub__grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
@media (max-width:1024px){ .ni-rhub__grid{ grid-template-columns:repeat(2,1fr); } }
@media (max-width:640px){ .ni-rhub__grid{ grid-template-columns:1fr; } }

/* ── Kartu ────────────────────────────────────────────────────────────── */
.ni-rhub__card{
  position:relative; overflow:hidden; display:block; text-decoration:none; color:inherit;
  background:var(--ni-bg-card,#fff); border:1px solid var(--ni-border,#e2e8f0);
  border-radius:14px; padding:20px; box-shadow:var(--ni-shadow-sm,0 1px 2px rgba(0,0,0,.05));
  opacity:0; animation:ni-rhub-in .4s ease forwards;
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.ni-rhub__card:hover{ transform:translateY(-4px); box-shadow:0 16px 28px -14px var(--rhub-shadow); border-color:transparent; }
.ni-rhub__card:focus-visible{ outline:2px solid var(--rhub-c1); outline-offset:2px; }
.ni-rhub__card-glow{
  position:absolute; right:-30px; top:-30px; width:110px; height:110px;
  background:radial-gradient(circle, var(--rhub-glow), transparent 70%); pointer-events:none;
}
.ni-rhub__card-icon{
  width:50px; height:50px; border-radius:14px; margin-bottom:14px;
  background:linear-gradient(135deg, var(--rhub-c1), var(--rhub-c2)); color:#fff;
  display:grid; place-items:center; box-shadow:0 6px 14px -4px var(--rhub-shadow);
}
.ni-rhub__card-icon svg{ width:25px; height:25px; }
.ni-rhub__card-title{ margin:0; font-size:.96875rem; font-weight:650; color:var(--ni-text,#1e293b); }
.ni-rhub__card-desc{ margin:5px 0 0; font-size:.78125rem; color:var(--ni-text-muted,#64748b); line-height:1.45; }
.ni-rhub__card-chip{
  display:inline-flex; align-items:center; gap:5px; margin-top:14px;
  font-size:.75rem; font-weight:600; color:var(--rhub-chip-fg); background:var(--rhub-chip-bg);
  padding:5px 11px; border-radius:999px; transition:gap .18s ease;
}
.ni-rhub__card-chip svg{ width:13px; height:13px; }
.ni-rhub__card:hover .ni-rhub__card-chip{ gap:9px; }

/* Stagger masuk (per grid, ≤3 kartu) */
.ni-rhub__grid .ni-rhub__card:nth-child(1){ animation-delay:0s; }
.ni-rhub__grid .ni-rhub__card:nth-child(2){ animation-delay:.06s; }
.ni-rhub__grid .ni-rhub__card:nth-child(3){ animation-delay:.12s; }

@keyframes ni-rhub-in{ from{ opacity:0; transform:translateY(8px); } to{ opacity:1; transform:none; } }

/* ── Responsif hero (mobile) ──────────────────────────────────────────── */
@media (max-width:640px){
  .ni-rhub__hero{ flex-wrap:wrap; padding:20px; gap:14px; }
  .ni-rhub__hero-count{ margin-left:0; text-align:left; width:100%; order:3; display:flex; align-items:baseline; gap:6px; }
  .ni-rhub__hero-count b{ font-size:1.25rem; }
}

/* ── Kurangi gerak ────────────────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce){
  .ni-rhub__card{ animation:none; opacity:1; transition:none; }
  .ni-rhub__card:hover{ transform:none; }
  .ni-rhub__card:hover .ni-rhub__card-chip{ gap:5px; }
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/report-hub.css
git commit -m "feat(css): add themed report-hub stylesheet"
```

---

## Task 2: Redesain hub Laporan Keuangan

**Files:**
- Modify (ganti seluruh isi): `templates/jurnal/laporan_keuangan_hub.html`

- [ ] **Step 1: Ganti seluruh isi file dengan berikut (persis)**

```django
{% extends 'base.html' %}
{% load static %}
{% block title %}Laporan Keuangan{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{% static 'css/report-hub.css' %}">
{% endblock %}

{% block content %}
<div class="ni-rhub ni-rhub--keuangan ni-animate-fade-in">
  <button type="button" class="ni-rhub__back" onclick="history.back()">
    <i data-lucide="arrow-left" aria-hidden="true"></i> Kembali
  </button>

  <div class="ni-rhub__hero">
    <div class="ni-rhub__hero-glow" aria-hidden="true"></div>
    <div class="ni-rhub__hero-icon" aria-hidden="true"><i data-lucide="bar-chart-2"></i></div>
    <div class="ni-rhub__hero-text">
      <h1 class="ni-rhub__hero-title">Laporan Keuangan</h1>
      <p class="ni-rhub__hero-sub">Semua laporan keuangan dalam satu tempat — pilih laporan untuk membuka.</p>
    </div>
    <div class="ni-rhub__hero-count"><b>6</b><span>Laporan</span></div>
  </div>

  <div class="ni-rhub__section-label"><span>Laporan Utama</span></div>
  <div class="ni-rhub__grid">
    <a href="{% url 'jurnal:laporan_laba_rugi' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="trending-up"></i></div>
      <h3 class="ni-rhub__card-title">Laporan Laba Rugi</h3>
      <p class="ni-rhub__card-desc">Pendapatan, beban, dan laba/rugi periode.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
    <a href="{% url 'jurnal:neraca' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="scale"></i></div>
      <h3 class="ni-rhub__card-title">Neraca</h3>
      <p class="ni-rhub__card-desc">Posisi aset, kewajiban, dan ekuitas.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
    <a href="{% url 'jurnal:laporan_perubahan_ekuitas' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="arrow-left-right"></i></div>
      <h3 class="ni-rhub__card-title">Laporan Perubahan Ekuitas</h3>
      <p class="ni-rhub__card-desc">Pergerakan modal selama periode.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
  </div>

  <div class="ni-rhub__section-label"><span>Buku &amp; Saldo</span></div>
  <div class="ni-rhub__grid">
    <a href="{% url 'jurnal:neraca_saldo' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="scale-3d"></i></div>
      <h3 class="ni-rhub__card-title">Neraca Saldo</h3>
      <p class="ni-rhub__card-desc">Trial balance — saldo tiap akun.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
    <a href="{% url 'jurnal:buku_besar' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="book-open"></i></div>
      <h3 class="ni-rhub__card-title">Buku Besar</h3>
      <p class="ni-rhub__card-desc">Mutasi per akun (general ledger).</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
  </div>

  <div class="ni-rhub__section-label"><span>Analisis</span></div>
  <div class="ni-rhub__grid">
    <a href="{% url 'jurnal:analisis_keuangan' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="line-chart"></i></div>
      <h3 class="ni-rhub__card-title">Analisis Keuangan</h3>
      <p class="ni-rhub__card-desc">Rasio &amp; indikator kinerja keuangan.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Verifikasi template kompilasi**

Run: `python manage.py check`
Expected: `System check identified no issues` (atau tanpa error terkait template). Bila muncul `TemplateSyntaxError` atau `NoReverseMatch`, perbaiki sebelum lanjut.

- [ ] **Step 3: Commit**

```bash
git add templates/jurnal/laporan_keuangan_hub.html
git commit -m "feat(ui): redesign financial report hub"
```

---

## Task 3: Redesain hub Laporan Persediaan

**Files:**
- Modify (ganti seluruh isi): `templates/inventory/laporan_hub.html`

- [ ] **Step 1: Ganti seluruh isi file dengan berikut (persis)**

```django
{% extends 'base.html' %}
{% load static %}
{% block title %}Laporan Persediaan{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{% static 'css/report-hub.css' %}">
{% endblock %}

{% block content %}
<div class="ni-rhub ni-rhub--persediaan ni-animate-fade-in">
  <button type="button" class="ni-rhub__back" onclick="history.back()">
    <i data-lucide="arrow-left" aria-hidden="true"></i> Kembali
  </button>

  <div class="ni-rhub__hero">
    <div class="ni-rhub__hero-glow" aria-hidden="true"></div>
    <div class="ni-rhub__hero-icon" aria-hidden="true"><i data-lucide="warehouse"></i></div>
    <div class="ni-rhub__hero-text">
      <h1 class="ni-rhub__hero-title">Laporan Persediaan</h1>
      <p class="ni-rhub__hero-sub">Semua laporan persediaan dalam satu tempat — pilih laporan untuk membuka.</p>
    </div>
    <div class="ni-rhub__hero-count"><b>6</b><span>Laporan</span></div>
  </div>

  <div class="ni-rhub__section-label"><span>Nilai &amp; Biaya</span></div>
  <div class="ni-rhub__grid">
    <a href="{% url 'inventory:laporan_valuasi' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="bar-chart-3"></i></div>
      <h3 class="ni-rhub__card-title">Valuasi Persediaan</h3>
      <p class="ni-rhub__card-desc">Nilai stok on-hand dari ledger.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
    <a href="{% url 'inventory:laporan_hpp' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="dollar-sign"></i></div>
      <h3 class="ni-rhub__card-title">Laporan HPP</h3>
      <p class="ni-rhub__card-desc">Harga pokok penjualan per periode.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
  </div>

  <div class="ni-rhub__section-label"><span>Pergerakan Stok</span></div>
  <div class="ni-rhub__grid">
    <a href="{% url 'inventory:stock_card' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="layout-grid"></i></div>
      <h3 class="ni-rhub__card-title">Kartu Stok</h3>
      <p class="ni-rhub__card-desc">Layer &amp; saldo per item.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
    <a href="{% url 'inventory:stock_ledger' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="book"></i></div>
      <h3 class="ni-rhub__card-title">Buku Persediaan</h3>
      <p class="ni-rhub__card-desc">Semua pergerakan + saldo berjalan.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
  </div>

  <div class="ni-rhub__section-label"><span>Analisis &amp; Ringkasan</span></div>
  <div class="ni-rhub__grid">
    <a href="{% url 'inventory:laporan_velocity' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="trending-up"></i></div>
      <h3 class="ni-rhub__card-title">Slow / Fast Moving</h3>
      <p class="ni-rhub__card-desc">Velocity item + realita gerakan.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
    <a href="{% url 'inventory:laporan_persediaan' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="file-text"></i></div>
      <h3 class="ni-rhub__card-title">Laporan Persediaan</h3>
      <p class="ni-rhub__card-desc">Ringkasan komprehensif.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Verifikasi template kompilasi**

Run: `python manage.py check`
Expected: tanpa error terkait template.

- [ ] **Step 3: Commit**

```bash
git add templates/inventory/laporan_hub.html
git commit -m "feat(ui): redesign inventory report hub"
```

---

## Task 4: Redesain hub Laporan Aset

**Files:**
- Modify (ganti seluruh isi): `templates/aset_tetap/laporan_aset_hub.html`

Catatan: hub ini hanya 2 laporan → grid rata **tanpa** label seksi (sesuai spec).

- [ ] **Step 1: Ganti seluruh isi file dengan berikut (persis)**

```django
{% extends 'base.html' %}
{% load static %}
{% block title %}Laporan Aset{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{% static 'css/report-hub.css' %}">
{% endblock %}

{% block content %}
<div class="ni-rhub ni-rhub--aset ni-animate-fade-in">
  <button type="button" class="ni-rhub__back" onclick="history.back()">
    <i data-lucide="arrow-left" aria-hidden="true"></i> Kembali
  </button>

  <div class="ni-rhub__hero">
    <div class="ni-rhub__hero-glow" aria-hidden="true"></div>
    <div class="ni-rhub__hero-icon" aria-hidden="true"><i data-lucide="building"></i></div>
    <div class="ni-rhub__hero-text">
      <h1 class="ni-rhub__hero-title">Laporan Aset</h1>
      <p class="ni-rhub__hero-sub">Semua laporan Aset Tetap dalam satu tempat — pilih laporan untuk membuka.</p>
    </div>
    <div class="ni-rhub__hero-count"><b>2</b><span>Laporan</span></div>
  </div>

  <div class="ni-rhub__grid" style="margin-top:20px;">
    <a href="{% url 'aset_tetap:laporan_register' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="building-2"></i></div>
      <h3 class="ni-rhub__card-title">Asset Register</h3>
      <p class="ni-rhub__card-desc">Daftar aset per kategori/lokasi/departemen.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
    <a href="{% url 'aset_tetap:laporan_penyusutan' %}" class="ni-rhub__card">
      <div class="ni-rhub__card-glow" aria-hidden="true"></div>
      <div class="ni-rhub__card-icon" aria-hidden="true"><i data-lucide="trending-down"></i></div>
      <h3 class="ni-rhub__card-title">Laporan Penyusutan</h3>
      <p class="ni-rhub__card-desc">Penyusutan per dimensi.</p>
      <span class="ni-rhub__card-chip">Lihat laporan <i data-lucide="arrow-right" aria-hidden="true"></i></span>
    </a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Verifikasi template kompilasi**

Run: `python manage.py check`
Expected: tanpa error terkait template.

- [ ] **Step 3: Commit**

```bash
git add templates/aset_tetap/laporan_aset_hub.html
git commit -m "feat(ui): redesign fixed-asset report hub"
```

---

## Task 5: Verifikasi visual & aksesibilitas (manual)

**Files:** tidak ada perubahan file — hanya pemeriksaan.

- [ ] **Step 1: Jalankan server dev**

Run: `python manage.py runserver`
Login, lalu buka tiap hub dari sidebar menu **Laporan**:
- `/jurnal/laporan-keuangan/`
- `/inventory/laporan/hub/`
- `/aset-tetap/laporan-aset/`

- [ ] **Step 2: Checklist visual (semua harus benar)**

- [ ] Ketiga hub menampilkan header hero bergradien dengan warna berbeda (Keuangan biru, Persediaan teal/hijau, Aset indigo).
- [ ] Hitungan di hero benar: Keuangan **6**, Persediaan **6**, Aset **2**.
- [ ] Ikon lucide muncul di hero, tiap kartu, chip (arrow-right), dan tombol Kembali (tidak ada kotak kosong / teks `data-lucide`).
- [ ] Keuangan & Persediaan punya 3 label seksi; Aset tanpa label seksi.
- [ ] Hover kartu: terangkat + bayangan berwarna kategori; chip melebar sedikit.
- [ ] Klik tiap kartu membuka laporan yang benar (14 tautan total). Tombol Kembali berfungsi.

- [ ] **Step 3: Checklist responsif & a11y**

- [ ] Kecilkan lebar browser < 640px: grid jadi 1 kolom; hero menumpuk (hitungan pindah ke bawah), tetap rapi.
- [ ] Tab keyboard ke kartu: ada outline fokus jelas.
- [ ] Aktifkan "reduce motion" OS: animasi masuk & efek hover-angkat tidak berjalan (kartu langsung terlihat).

- [ ] **Step 4: Konfirmasi tidak ada perubahan Python**

Run: `git diff --name-only HEAD~4 HEAD`
Expected: hanya `static/css/report-hub.css` + 3 template `.html` + (dokumen plan/spec bila di-commit). Tidak ada file `.py`.

---

## Catatan Verifikasi Rencana (self-review penulis)

- **Cakupan spec:** Task 1 = CSS/tema (spec §3,§4,§5,§7); Task 2–4 = isi tiap hub + pengelompokan (spec §6); Task 5 = kriteria penerimaan (spec §8). Semua tercakup.
- **Tanpa placeholder:** seluruh CSS & markup lengkap; tiap `{% url %}` sudah diverifikasi ada di `urls.py`.
- **Konsistensi nama kelas:** kelas `.ni-rhub-*` yang dipakai di template semua terdefinisi di Task 1 (`__hero`, `__hero-glow`, `__hero-icon`, `__hero-text`, `__hero-title`, `__hero-sub`, `__hero-count`, `__back`, `__section-label`, `__grid`, `__card`, `__card-glow`, `__card-icon`, `__card-title`, `__card-desc`, `__card-chip`).
- **Deviasi kecil dari spec:** tombol Kembali diletakkan sebagai link breadcrumb **di atas** hero (bukan di dalam hero) demi kerapian & mobile — tetap `history.back()`.
```
