// Icons + category palette. Exports to window.
const Icon = ({ d, size = 22, sw = 2, fill = 'none', children, style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" style={style}>
    {d ? <path d={d} /> : children}
  </svg>
);

const I = {
  search: (p) => <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></Icon>,
  scan: (p) => <Icon {...p}><path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" /><path d="M7 7v10M10 7v10M13 7v10M17 7v10" sw="1.6" /></Icon>,
  plus: (p) => <Icon {...p}><path d="M12 5v14M5 12h14" /></Icon>,
  minus: (p) => <Icon {...p}><path d="M5 12h14" /></Icon>,
  trash: (p) => <Icon {...p}><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6" /></Icon>,
  sliders: (p) => <Icon {...p}><path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="8" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></Icon>,
  cart: (p) => <Icon {...p}><circle cx="9" cy="20" r="1.4" /><circle cx="18" cy="20" r="1.4" /><path d="M2 3h2.5l2.2 12.4a2 2 0 0 0 2 1.6h7.8a2 2 0 0 0 2-1.6L21.5 7H6" /></Icon>,
  cash: (p) => <Icon {...p}><rect x="2" y="6" width="20" height="12" rx="2" /><circle cx="12" cy="12" r="2.6" /><path d="M6 9v0M18 15v0" /></Icon>,
  card: (p) => <Icon {...p}><rect x="2" y="5" width="20" height="14" rx="2.5" /><path d="M2 10h20M6 15h4" /></Icon>,
  qris: (p) => <Icon {...p}><rect x="3" y="3" width="7" height="7" rx="1.4" /><rect x="14" y="3" width="7" height="7" rx="1.4" /><rect x="3" y="14" width="7" height="7" rx="1.4" /><path d="M14 14h3v3M21 14v0M17 21h4v-4M14 21v0" /></Icon>,
  close: (p) => <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>,
  check: (p) => <Icon {...p}><path d="M5 12.5 10 17 19 7" /></Icon>,
  check3: (p) => <Icon {...p} sw="3"><path d="M5 12.5 10 17 19 7" /></Icon>,
  pause: (p) => <Icon {...p}><rect x="7" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none" /><rect x="14" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none" /></Icon>,
  ban: (p) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="m6 6 12 12" /></Icon>,
  receipt: (p) => <Icon {...p}><path d="M5 3v18l2-1.4L9 21l2-1.4L13 21l2-1.4L17 21l2-1.4V3l-2 1.4L15 3l-2 1.4L11 3 9 4.4 7 3 5 4.4Z" /><path d="M8 8h8M8 12h8M8 16h5" sw="1.6" /></Icon>,
  tag: (p) => <Icon {...p}><path d="M3 7v5.2a2 2 0 0 0 .6 1.4l7.8 7.8a2 2 0 0 0 2.8 0l5.2-5.2a2 2 0 0 0 0-2.8L11.6 5.6A2 2 0 0 0 10.2 5H5a2 2 0 0 0-2 2Z" /><circle cx="7.5" cy="9.5" r="1.3" fill="currentColor" stroke="none" /></Icon>,
  store: (p) => <Icon {...p}><path d="M4 9V5h16v4M4 9l-1 0a1 1 0 0 0 0 2 2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 1 1 0 0 0 0-2l-1 0M5 11.5V20h14v-8.5" /></Icon>,
  chevR: (p) => <Icon {...p}><path d="m9 6 6 6-6 6" /></Icon>,
  clock: (p) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></Icon>,
  user: (p) => <Icon {...p}><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></Icon>,
  back: (p) => <Icon {...p}><path d="M15 6l-6 6 6 6" /></Icon>,
};

// Per-category visual palette (gradient for thumbs, solid for accents)
const CAT_PALETTE = {
  kopi:      { g: ['oklch(0.55 0.09 55)', 'oklch(0.42 0.08 45)'], solid: 'oklch(0.52 0.09 50)' },
  noncoffee: { g: ['oklch(0.62 0.11 150)', 'oklch(0.50 0.10 158)'], solid: 'oklch(0.56 0.10 152)' },
  makanan:   { g: ['oklch(0.66 0.13 45)', 'oklch(0.55 0.14 35)'], solid: 'oklch(0.60 0.13 40)' },
  pastry:    { g: ['oklch(0.72 0.11 75)', 'oklch(0.62 0.12 65)'], solid: 'oklch(0.66 0.11 70)' },
  retail:    { g: ['oklch(0.56 0.08 280)', 'oklch(0.46 0.09 285)'], solid: 'oklch(0.52 0.08 282)' },
};
const catColor = (c) => CAT_PALETTE[c] || CAT_PALETTE.kopi;

Object.assign(window, { Icon, I, CAT_PALETTE, catColor });
