# Handoff: Naveda Kasir — Point of Sale (POS) Screen

## Overview
A tablet-first **cashier (Kasir) POS screen** for an Indonesian café/retail business ("Naveda Kopi"). It is the single screen a cashier uses for an entire transaction: browse the product catalog, build an order ticket, apply modifiers/discounts, take payment (cash / card / QRIS), and confirm. It is backed by a standard Django **sales** module but is intentionally designed for an employee with **no accounting knowledge** — everything for one transaction lives on one screen, with no navigation tree and (almost) no modals.

Language of the UI is **Indonesian**. Currency is **Indonesian Rupiah (IDR)** formatted as `Rp 28.000` (thousands separated by `.`, no decimals).

## About the Design Files
The files in this bundle are **design references created in HTML/React+Babel** — an interactive prototype showing the intended look and behavior. They are **not production code to copy directly**. The task is to **recreate this design in the target codebase's environment** (the existing Django `sales` app + whatever frontend stack it uses — server-rendered templates, HTMX, React, Vue, etc.), wiring it to the real models and endpoints. Use the codebase's established patterns, component library, and conventions. If no frontend environment exists yet, pick the most appropriate stack for the project and implement there.

The prototype's sample data (`data.js`) mirrors the real model shape so you can map fields 1:1 — see **Data Mapping** below.

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, radii, shadows, and interactions are all specified. Recreate the UI to match, using the codebase's existing libraries where they exist. The locked visual direction is:
- **Theme: Cool** (soft slate / blue-grey neutrals, blue accent)
- **Density: Comfy**
- **Product cards: Photo** (image thumbnail on each card)

The prototype contains other theme/density/card variants behind a "Tweaks" dev panel — **ignore those**; only the Cool/Comfy/Photo combination is in scope. The tokens listed below are the Cool theme values.

---

## Layout

Fixed tablet canvas **1366 × 1024** (landscape, 4:3-ish iPad). Two-column CSS grid:

```
grid-template-columns: 1fr 452px;   /* catalog | order ticket */
```

- **Left — Catalog** (`1fr`): vertical flex column → brandbar, search bar, category pill row, scrollable product grid.
- **Right — Order Ticket** (`452px` fixed): vertical flex column → header, scrollable line-item list, sticky totals + tender + action footer. Elevated with a left-edge shadow: `box-shadow: -14px 0 34px rgba(40,30,20,.06)`.
- **Overlays** slide in over the right edge (modifiers, held bills, discount). A numpad sheet slides **up** from the bottom of the ticket. A full-screen success state covers the tablet. None of these are centered modals — they are edge-anchored panels.

The whole tablet is scaled with `transform: scale()` to fit the viewport and letterboxed on a dark background. In a real responsive web app you would drop the fixed-canvas scaling and instead make the grid responsive (the ticket can collapse to a bottom sheet on narrow screens), but the **1366×1024 proportions are the design target**.

---

## Screens / Views

### 1. Catalog (left column)

**Brandbar** (top): `Plus Jakarta Sans` 800. A 46×46 rounded-14px gradient logo mark ("N"), brand name "Naveda Kasir" + sub-line "Naveda Kopi · Outlet Senopati". Right side: three pill "chips" (44px tall, `--surface`, `--shadow-sm`, radius 13px):
- **Tertahan** (held bills) — pause icon + label + count badge; opens the Held panel.
- **Cashier** — green status dot + user icon + name ("Dewi A.").
- **Clock** — live `HH:MM`.

**Search bar**: 60px tall, radius 18px, `--surface`. Search icon (24px, `--ink-faint`), input placeholder "Cari produk atau scan barcode…", a clear-✕ button when non-empty, and a **Scan** button (44px, `--accent-soft` bg, `--accent-deep` text, barcode icon). On focus the bar gets a 1.5px `--accent` border + `--shadow-md`. Search filters by product **name OR code** (`kode_item`), case-insensitive.

**Category pills** (horizontal scroll, hidden scrollbar): 46px tall, radius 14px. Each shows label + count. Active pill = `--ink` background, `--surface` text. Categories: `Semua, Kopi, Non-Coffee, Makanan, Pastry, Retail`.

**Product grid**: `repeat(auto-fill, minmax(176px, 1fr))`, gap 16px, scrollable. Each **product card** (`.pcard`, radius 16px, `--surface`, `--shadow-sm`, lifts `translateY(-3px)` + `--shadow-md` on hover, presses on `:active`):
- **Photo thumb** 104px tall — a striped placeholder (`repeating-linear-gradient` 45°) with a small mono "product shot" chip. *In production, replace with the item's real image; fall back to a category-colored block with the item's initial (see `block` card style in CSS) if no image.*
- **Pilihan flag** (top-right): shown only if the item has modifier groups — sliders icon + "Pilihan".
- **Qty bubble** (top-left): green pill showing how many of this item are already in the cart (only when > 0).
- Body: product **name** (700, 14.5px, balanced wrap), **code** (`kode_item`, mono 11px `--ink-faint`), **price** (`rp(selling_price)`, 800, 16px, pushed to bottom).
- On tap: items **with** modifier groups open the Modifier panel; items **without** are added straight to the cart (with a confirmation toast).

Empty search result → centered "Tidak ada produk yang cocok. Coba kata kunci lain."

### 2. Order Ticket (right column)

**Header**: "Pesanan" (800, 19px) + transaction id `TRX-SAL-048` (mono 12px). Right: item-count chip ("`N` item").

**Line-item list** (scrollable, gap 8px). Each line (`.line`, radius 16px, 1px `--line-soft` border, `--shadow-sm`, `lineIn` slide-fade-in animation):
- Top row: product **name** (700, 15px); under it, selected **modifier labels** (11.5px `--ink-soft`; price adds shown as `+Rp …` in `--accent-deep` bold). Right: **line total** (800, 15px).
- Bottom row: a **stepper** — `−` button (`--danger` colored) / qty / `+` button, each 38px tap target inside a 12px-radius `--surface-2` track; an **"Ubah"** (edit) button if the item has modifiers (re-opens the panel pre-filled); a red **trash** button (40px, `--danger-soft` bg, `--danger` icon) pushed to the right. Decrementing below 1 removes the line.

Empty cart → centered cart icon + "Belum ada pesanan" + helper line.

**Totals footer** (sticky, `--shadow-up` top shadow):
- `Subtotal` — sum of line totals.
- `PPN 11%` — Indonesian VAT on (subtotal − discount).
- **Discount row** — "Tambah diskon" tag button when none; when set, shows "Diskon `10%`" and `−Rp …` in `--accent-deep`.
- **Grand total** (`.grand`): `--surface-2` block, radius 16px, "Total Bayar" label + **34px / 800** total (the largest number on screen).

**Tender selector**: three equal buttons (60px tall, radius 14px, 2px border) — **Tunai** (cash), **Kartu EDC** (card), **QRIS**. Selected = `--accent` border + `--accent-soft` bg + `--accent-deep` text/icon. Default selection: Tunai.

**Pay button** (`.pay-btn`): 78px tall, radius 22px, **green gradient** `linear-gradient(180deg, var(--pay), var(--pay-deep))`, white. Left: check icon + "Selesaikan" eyebrow + grand total. Right: chevron. Glowing green shadow, brightens on hover, presses down on `:active`. Disabled (greyed) when cart empty. **This is the biggest, most prominent control on the screen.**

**Secondary actions** (row): **Batalkan** (Void) — `--danger-soft` bg / `--danger` text, ban icon. **Tahan** (Hold) — outline (2px `--line`) / `--hold` muted blue-grey text, pause icon. Both disabled when cart empty.

### 3. Modifier panel (slide-in from right, NOT a modal)

Width 560px, slides in with `translateX` + scrim. Header: back-arrow ✕, product name, "Rp … · pilih opsi di bawah". Body lists each **modifier group**:
- Group header: name + a **rule badge** — red "Wajib" if required, grey "Opsional · maks N" if optional with a max.
- Options in a 2-col grid. Each option (`.mopt`, radius 16px, 2px border): a radio/check circle, option name, and `+Rp …` add-price (only if > 0). Selected = `--accent` border + `--accent-soft` bg; the circle fills `--accent` with a white check.
- **Single-select** groups (`max == 1`) behave like radios; **multi-select** respect the group's `max`.
- A **Jumlah** (quantity) stepper at the bottom.

Footer: "Batal" + a green confirm button showing live line total ("Tambah" / "Simpan" when editing). Defaults are pre-selected from each option's `is_default` (and the first option of a required group if none defaulted).

### 4. Held bills panel (slide-in)
List of suspended orders (`.held-card`): pause-icon avatar, label ("Meja 4", "Take Away — Budi"), "`N` item · HH:MM", total, a red trash, and a dark **"Lanjutkan"** (resume) button. Resuming restores that order's full cart (with regenerated line ids) and removes it from the tray. Holding the current bill snapshots it here and clears the active sale.

### 5. Discount panel (slide-in, 460px)
Two groups: **Persentase** (Tanpa, 5/10/15/20/25 %) and **Nominal** (Rp 10.000 / 25.000 / 50.000) as selectable tiles. Applying sets the discount and closes; "Tanpa" clears it. Nominal discount is capped at subtotal.

### 6. Cash numpad (slide-up sheet)
Triggered by paying while **Tunai** is selected. Slides up over the ticket footer with scrim. Shows **Uang diterima** (amount tendered) and a **Kembalian/Kurang** (change/short) row that turns green when sufficient, red when short. Quick-amount buttons: "Uang Pas" (exact), next 50k, next 100k. 3×4 keypad (1–9, 000, 0, ⌫). Green "Konfirmasi Pembayaran" enabled only when tendered ≥ total. Card/QRIS skip the numpad and finalize directly.

### 7. Payment success (full-screen state)
Covers the tablet. Green check ring (pop animation), "Pembayaran Berhasil", an amounts block (Total, Metode + amount, and **Kembalian** highlighted green for cash), the `TRX-SAL-…` id pill, and two buttons: "Cetak Struk" (print receipt) and green **"Transaksi Baru"** (new sale → clears cart, increments the TRX sequence).

### Toast
Small dark pill bottom-center for lightweight confirmations ("… ditambahkan", "Diskon diterapkan", "Pesanan ditahan", etc.), auto-dismiss ~2.2s.

---

## Interactions & Behavior

- **Add to cart**: tap card → if `modifier_groups.length` open Modifier panel, else add directly + toast.
- **Line merge**: adding an item whose item + exact modifier selection signature matches an existing line **increments that line** instead of creating a duplicate. Signature = `item_pk | groupPk:sortedOptionPks | …`.
- **Qty**: `+`/`−` on the line; `−` at qty 1 removes the line. Trash removes immediately (no confirm — touch-fast).
- **Edit modifiers**: "Ubah" reopens the panel pre-filled; confirming replaces that line's selection in place (keeps line id).
- **Discount** recomputes PPN on the discounted base.
- **Hold**: snapshots current cart → held tray, clears sale. **Resume**: loads a held order back into the cart.
- **Void**: clears the current cart (no TRX increment).
- **Pay**: cash → numpad → success; card/QRIS → success directly. **New sale** increments `TRX-SAL` sequence.
- **Transitions** (durations/easing as built):
  - Overlays: `transform .3s cubic-bezier(.32,.72,0,1)`; scrims `opacity .24s`.
  - Numpad sheet: `transform .26s cubic-bezier(.4,0,.2,1)`.
  - Line item in: `.22s ease` fade+slide. Card hover: `.12s`. Success ring: `.4s` pop. Toast: `.25s`.
- **Touch targets**: steppers 38px, trash 40px, tenders 60px, pay 78px, numpad keys 56px — keep ≥44px for primary taps. No keyboard shortcuts assumed.

## State Management
Per-sale state needed:
- `cart`: array of lines `{ lineId, item, qty, selections, sig, modLabels, unitPrice, lineTotal }`.
- `tender`: `'cash' | 'card' | 'qris'`.
- `discount`: `null | { type: 'pct'|'amt', val }`.
- `trxSeq`: integer → renders `TRX-SAL-###`.
- `held`: array of held orders `{ id, label, time, count, total, cart }`.
- Transient UI: modifier panel `{ open, item, isEdit, lineId, selections, qty }`, held/discount panel open flags, numpad `{ open, value }`, success `{ open, data }`, toast.

Derived each render: `subtotal = Σ lineTotal`, `discAmt`, `taxedBase = max(0, subtotal − discAmt)`, `tax = round(taxedBase × 0.11)`, `total = taxedBase + tax`, and a per-item cart-qty map for the card bubbles.

**Data fetching (production)**: load catalog items + their modifier groups for the active store/outlet; on pay, POST the order to the `sales` module (create `SalesHeader` + `SalesItem` rows, the module handles FIFO outflow, PPN, and journals). See Data Mapping.

## Data Mapping (prototype → Django `sales` models)
The prototype `item` shape maps to the real inventory/sales models:
- `item.item_pk` → inventory item PK
- `item.name`, `item.kode_item` → item name / code
- `item.selling_price` → unit selling price (IDR)
- `item.category` → category/group for the pill filter
- `item.modifier_groups[]` → `{ pk, nama, is_required, min, max (or max_selections), options[] }`
- `option` → `{ pk, name, additional_price, is_default }`
- `POS_TAX_RATE = 0.11` → PPN; transaction id format `TRX-SAL-###` matches the module's existing scheme (`SalesHeader`).

Confirm exact field names against `sales/models.py` (the prototype mirrors them but the real fields may differ slightly, e.g. modifier max stored as `max_selections`).

## Design Tokens — Cool theme (the locked direction)
Defined as CSS custom properties (see `styles.css`, `[data-theme="cool"]`). Values are in **oklch**; approximate hex in comments for convenience.

**Neutrals / surfaces**
- `--bg: oklch(0.965 0.007 248)`  (~`#eef0f4`) — app background (soft, never pure white)
- `--surface: oklch(0.996 0.003 252)` (~`#fdfdff`) — cards/panels
- `--surface-2: oklch(0.978 0.006 248)` (~`#f4f6f9`) — insets/tracks
- `--ink: oklch(0.27 0.020 256)` (~`#2b303a`) — primary text
- `--ink-soft: oklch(0.50 0.022 254)` (~`#646b78`) — secondary text
- `--ink-faint: oklch(0.66 0.018 254)` (~`#9aa0ab`) — tertiary/placeholder
- `--line: oklch(0.905 0.012 250)` (~`#dde0e7`) — borders
- `--line-soft: oklch(0.935 0.009 250)` (~`#e7e9ef`) — subtle borders

**Accent (Cool = blue)** — active states, pills, highlights, selected options
- `--accent: oklch(0.595 0.13 250)` (~`#3b6ef5`)
- `--accent-deep: oklch(0.50 0.13 252)` (~`#2f57c9`)
- `--accent-soft: oklch(0.935 0.04 250)` (~`#e3eafd`)
- `--accent-ink: oklch(0.99 0.005 250)` (~`#ffffff`)

**Semantic (constant across all themes — color psychology)**
- Pay / success **green**: `--pay: oklch(0.63 0.15 150)` (~`#1f9d57`), `--pay-deep: oklch(0.55 0.15 150)` (~`#16823f`), `--pay-soft: oklch(0.93 0.05 150)` (~`#d9f3e3`)
- Destructive **red**: `--danger: oklch(0.595 0.18 27)` (~`#dc4c3e`), `--danger-soft: oklch(0.94 0.045 27)` (~`#fbe3df`)
- Hold/neutral **muted blue-grey**: `--hold: oklch(0.52 0.035 252)` (~`#5f6b7d`), `--hold-soft: oklch(0.94 0.02 252)`

**Radii**: `--r-sm 10px`, `--r-md 16px`, `--r-lg 22px`, `--r-xl 28px`. Cards 16px, pay button 22px, panels/sheets 28px, chips/pills 13–14px.

**Shadows**
- `--shadow-sm: 0 1px 2px rgba(40,30,20,.05), 0 2px 6px rgba(40,30,20,.05)`
- `--shadow-md: 0 4px 12px rgba(40,30,20,.07), 0 10px 28px rgba(40,30,20,.07)`
- `--shadow-lg: 0 8px 22px rgba(40,30,20,.10), 0 24px 60px rgba(40,30,20,.12)`
- `--shadow-up: 0 -10px 30px rgba(40,30,20,.10)` (sticky footers / sheets)

**Typography**: `Plus Jakarta Sans` (Google Fonts), weights 400/500/600/700/800.
- Brand / panel titles 800, 18–22px. Section/line names 700, 14.5–16px. Body/labels 500–600, 13–14px. Codes mono 11px.
- Grand total 800, 34px. Pay amount 800, ~22–24px. Numpad value 800, 30px.
- **All currency and numeric values use `font-variant-numeric: tabular-nums`** (class `.tnum`) so digits align.
- Letter-spacing: tighten large headings ~`-0.01em` to `-0.02em`.

**Currency formatting**: `rp(n) = 'Rp ' + Math.round(n).toLocaleString('id-ID')` → `Rp 28.000`. Uses a non-breaking space after "Rp".

## Spacing
8px-based rhythm. Catalog padding 22–26px; grid gap 16px (12px in compact); ticket list padding 10–16px, gap 8px; footer padding 14–18px, gap 12px; overlay body padding 18–24px, gap 20px.

## Assets
- **Font**: Plus Jakarta Sans via Google Fonts (`@import` in `styles.css`).
- **Icons**: inline SVG stroke icons defined in `icons.jsx` (search, barcode/scan, plus, minus, trash, sliders, cart, cash, card, qris, close, check, pause, ban, receipt, tag, store, chevron, clock, user, back). Replace with the codebase's icon set if it has one (Lucide/Heroicons map cleanly).
- **Product images**: none real — photo cards use striped placeholders. Wire to real item images in production; keep the category-color-block + initial as the no-image fallback.
- No raster/brand assets included.

## Files
Design reference files (in this bundle, under `design_files/`):
- `Naveda Kasir.html` — entry point; loads React 18 + Babel and the scripts below.
- `styles.css` — all tokens, themes, and component styles.
- `data.js` — sample catalog, categories, modifier groups, tax rate, held seeds, `rp()` helper (mirrors the real model shape).
- `icons.jsx` — SVG icon set + per-category color palette.
- `catalog.jsx` — left column (brandbar, search, pills, product grid, cards).
- `ticket.jsx` — right column (line items, totals, tenders, pay/void/hold) + slide-up numpad.
- `overlays.jsx` — modifier panel, held-bills panel, discount panel, success state, toast.
- `app.jsx` — state, pricing/modifier logic, all flows. **Note:** `TWEAK_DEFAULTS` is locked to `{ theme: 'cool', density: 'comfy', cardStyle: 'photo' }`; the theme/density/card variants and the Tweaks panel are prototype-only dev tooling — implement only the Cool/Comfy/Photo direction.

To run the reference locally: open `Naveda Kasir.html` in a browser (it loads React/Babel from CDN; needs internet).
