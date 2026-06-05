// Catalog: brandbar, search + barcode, category pills, product grid
function Catalog({ store, items, categories, query, setQuery, activeCat, setActiveCat,
                   cardStyle, onTapItem, cartQtyByItem, heldCount, onOpenHeld, now }) {

  const counts = React.useMemo(() => {
    const m = { all: items.length };
    items.forEach((it) => { m[it.category] = (m[it.category] || 0) + 1; });
    return m;
  }, [items]);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((it) => {
      if (activeCat !== 'all' && it.category !== activeCat) return false;
      if (!q) return true;
      return it.name.toLowerCase().includes(q) || it.kode_item.toLowerCase().includes(q);
    });
  }, [items, query, activeCat]);

  return (
    <div className="catalog">
      <div className="cat-top">
        <div className="brandbar">
          <div className="brand-mark">N</div>
          <div className="brand-meta">
            <div className="brand-name">Naveda Kasir</div>
            <div className="brand-sub">{store.name} · {store.outlet}</div>
          </div>
          <div className="brandbar-right">
            <button className="chip held-chip" onClick={onOpenHeld}>
              <I.pause size={17} />
              <span>Tertahan</span>
              {heldCount > 0 && <span className="badge tnum">{heldCount}</span>}
            </button>
            <div className="chip">
              <span className="dot"></span>
              <I.user size={16} />
              <b>{store.cashier}</b>
            </div>
            <div className="chip tnum"><I.clock size={16} />{now}</div>
          </div>
        </div>

        <div className="searchbar">
          <I.search size={24} style={{ color: 'var(--ink-faint)' }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cari produk atau scan barcode…"
          />
          {query && (
            <button className="np-x" style={{ width: 40, height: 40 }} onClick={() => setQuery('')}>
              <I.close size={18} />
            </button>
          )}
          <button className="scan-btn"><I.scan size={20} />Scan</button>
        </div>
      </div>

      <div className="pillbar no-scrollbar">
        {categories.map((c) => (
          <button
            key={c.id}
            className={'pill' + (activeCat === c.id ? ' active' : '')}
            onClick={() => setActiveCat(c.id)}
          >
            {c.label}
            <span className="cnt tnum">{counts[c.id] || 0}</span>
          </button>
        ))}
      </div>

      <div className="grid-wrap thin-scroll">
        {filtered.length === 0 ? (
          <div className="grid-empty">Tidak ada produk yang cocok.<br />Coba kata kunci lain.</div>
        ) : (
          <div className="pgrid">
            {filtered.map((it) => (
              <ProductCard
                key={it.item_pk}
                item={it}
                cardStyle={cardStyle}
                qty={cartQtyByItem[it.item_pk] || 0}
                onTap={() => onTapItem(it)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ProductCard({ item, cardStyle, qty, onTap }) {
  const [pulse, setPulse] = React.useState(0);
  const pal = catColor(item.category);
  const hasMods = item.modifier_groups && item.modifier_groups.length > 0;
  const handle = () => { setPulse((p) => p + 1); onTap(); };
  const initial = item.name.replace(/^(Es|Kopi)\s+/i, '').trim()[0] || item.name[0];

  return (
    <button className="pcard" style={{ '--cat': pal.solid }} onClick={handle}>
      {qty > 0 && <span className="qty-bubble tnum">{qty}</span>}
      {hasMods && <span className="mod-flag"><I.sliders size={12} sw="2.4" />Pilihan</span>}
      <div
        className={'thumb' + (cardStyle === 'photo' ? ' photo' : '')}
        style={cardStyle === 'photo' ? null : { background: `linear-gradient(150deg, ${pal.g[0]}, ${pal.g[1]})` }}
      >
        {cardStyle === 'photo'
          ? <span className="ph-label">product shot</span>
          : <span className="initial">{initial.toUpperCase()}</span>}
      </div>
      <div className="body">
        <div className="pname">{item.name}</div>
        <div className="pcode">{item.kode_item}</div>
        <div className="pprice tnum">{rp(item.selling_price)}</div>
      </div>
      {pulse > 0 && <span key={pulse} className="pulse"></span>}
    </button>
  );
}

Object.assign(window, { Catalog });
