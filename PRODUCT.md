# Naveda Integra — Design Context

## Design Context

### Users

Diverse Indonesian business operators across SME segments: warung and toko owners, UMKM (micro/small/medium enterprise) entrepreneurs, hotel owners, restaurant operators, in-house accountants and finance staff at SMEs, and bookkeepers managing multiple client businesses. They range from financially literate to non-accountant operators who just need to know where their money went.

**Context when using the product:** During business hours or at end-of-day, often on a desktop or laptop in an office or back-of-house setting. The primary job is recording transactions, reviewing balances, and generating reports — tasks that require concentration and trust in the output.

**Language and locale:** All UI in Bahasa Indonesia. Timezone: Asia/Jakarta. Currency: IDR.

### Brand Personality

**Structured, dependable, easy to use.**

- **Structured**: The interface should feel organized and purposeful. Information has clear hierarchy. Nothing feels out of place.
- **Dependable**: Users trust the numbers. The design must signal accuracy — clean alignment, consistent spacing, predictable patterns. No decorative noise that distracts from data.
- **Easy to use**: Non-accountants (hotel owners, warung operators) should not feel intimidated. The interface reveals complexity gradually, starting with the most common tasks.

### Emotional Goals

After completing a task in Naveda Integra, users should feel:
- **Confident** — the numbers are correct and they can see why
- **Proud** — this is a professional tool; using it makes their business feel properly managed

### Aesthetic Direction

**Refined utilitarian** — clean and highly structured, like a well-printed annual report or a premium bank's internal dashboard. Not a consumer app. Not an old ERP. Somewhere between: "a tool built by people who respect their users' time" and "an interface that makes you look competent when you share a screenshot."

**Visual tone:** Calm authority. Generous whitespace where it aids comprehension, compact where density serves data review (tables, journals). Restrained use of color — data is the focus, not decoration.

**Theme:** Both light and dark modes supported via system preference toggle. Light mode is the primary/default; dark mode for extended sessions (bookkeepers, accountants working late).

### Anti-References

- **Consumer fintech** (glossy, gradient-heavy, animated) — avoid. Naveda is a work tool, not a spending tracker.
- **Old Enterprise ERP** (SAP-style dense gray grids) — avoid. Must feel modern and considered, not like a system from 2005.

### Design Principles

1. **Data is the product.** Typography, spacing, and alignment exist to make numbers legible and trustworthy. Decoration that doesn't serve comprehension is removed.
2. **Progressive complexity.** The most common tasks (record a transaction, check a balance) are immediately visible. Advanced features are discoverable but never intrusive.
3. **Approachable professionalism.** Professional enough to feel credible for a hotel's finance team. Accessible enough that a warung owner doesn't need an accounting degree to navigate.
4. **Predictable patterns.** Consistent component behavior builds trust. Users should never have to guess how something works the second time they use it.
5. **Local-first.** Bahasa Indonesia, IDR formatting, Jakarta timezone, Indonesian business naming conventions — all treated as first-class, not afterthoughts.

### Technical Constraints

- Django 6.x template-rendered pages (no SPA/React)
- Custom CSS design system with `ni-` prefix (modular CSS files)
- Lucide icons (0.460.0 via CDN)
- Chart.js 4.x for charts (dashboard only)
- Current font: Inter (to be replaced — it is on the banned reflex list; future design work should select a new font stack)
- Current brand color: `#0054a6` (primary blue) — can evolve in palette refinements
- No new dependencies without explicit approval
- WCAG 2.1 AA minimum contrast compliance
