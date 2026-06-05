// Naveda Kasir — main app: state, pricing, flows, tweaks

// ----- pricing / modifier helpers -----
function defaultSelections(item) {
  const sel = {};
  (item.modifier_groups || []).forEach((g) => {
    const single = (g.max_selections === 1) || (g.max === 1);
    const defs = g.options.filter((o) => o.is_default).map((o) => o.pk);
    if (single) {
      sel[g.pk] = defs.length ? [defs[0]] : (g.is_required && g.options.length ? [g.options[0].pk] : []);
    } else {
      sel[g.pk] = defs;
    }
  });
  return sel;
}
function optById(item, pk) {
  for (const g of (item.modifier_groups || [])) {
    const o = g.options.find((x) => x.pk === pk);
    if (o) return { o, g };
  }
  return null;
}
function unitPrice(item, selections) {
  let p = Number(item.selling_price);
  Object.values(selections || {}).flat().forEach((pk) => {
    const f = optById(item, pk);
    if (f) p += Number(f.o.additional_price);
  });
  return p;
}
function modLabelsFor(item, selections) {
  const out = [];
  (item.modifier_groups || []).forEach((g) => {
    (selections[g.pk] || []).forEach((pk) => {
      const o = g.options.find((x) => x.pk === pk);
      if (!o) return;
      const add = Number(o.additional_price);
      if (add > 0 || !o.is_default) out.push({ name: o.name, add: add > 0 ? add : 0 });
    });
  });
  return out;
}
function selSignature(item_pk, selections) {
  const parts = Object.keys(selections).sort().map((k) => k + ':' + [...selections[k]].sort().join(','));
  return item_pk + '|' + parts.join('|');
}
function buildLine(item, selections, qty) {
  const up = unitPrice(item, selections);
  return {
    lineId: 'L' + Math.random().toString(36).slice(2, 9),
    item, qty, selections,
    sig: selSignature(item.item_pk, selections),
    modLabels: modLabelsFor(item, selections),
    unitPrice: up,
    lineTotal: up * qty,
  };
}

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "cool",
  "density": "comfy",
  "cardStyle": "photo"
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  const [query, setQuery] = React.useState('');
  const [activeCat, setActiveCat] = React.useState('all');
  const [cart, setCart] = React.useState([]);
  const [tender, setTender] = React.useState('cash');
  const [discount, setDiscount] = React.useState(null); // {type:'pct'|'amt', val}
  const [trxSeq, setTrxSeq] = React.useState(48);

  const [held, setHeld] = React.useState(() => POS_HELD_SEED.map((h, i) => {
    // give seeds real cart snapshots so "Lanjutkan" actually restores them
    const picks = i === 0
      ? [[POS_ITEMS[0], 2], [POS_ITEMS[20], 1]]
      : [[POS_ITEMS[3], 1], [POS_ITEMS[21], 1]];
    const snap = picks.map(([it, q]) => buildLine(it, defaultSelections(it), q));
    const tot = snap.reduce((s, l) => s + l.lineTotal, 0);
    return { ...h, cart: snap, count: snap.reduce((s, l) => s + l.qty, 0), total: Math.round(tot * (1 + POS_TAX_RATE)) };
  }));

  const [modPanel, setModPanel] = React.useState({ open: false, item: null, isEdit: false, lineId: null, selections: {}, qty: 1 });
  const [heldOpen, setHeldOpen] = React.useState(false);
  const [discOpen, setDiscOpen] = React.useState(false);
  const [numpad, setNumpad] = React.useState({ open: false, value: '' });
  const [success, setSuccess] = React.useState({ open: false, data: null });
  const [toast, setToast] = React.useState({ msg: '', Ico: null, k: 0 });
  const [now, setNow] = React.useState(fmtTime());

  React.useEffect(() => {
    const id = setInterval(() => setNow(fmtTime()), 10000);
    return () => clearInterval(id);
  }, []);

  // toast auto-dismiss
  const toastTimer = React.useRef(null);
  function showToast(msg, Ico) {
    setToast({ msg, Ico, k: Date.now() });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast((s) => ({ ...s, msg: '' })), 2200);
  }

  const trxId = 'TRX-SAL-' + String(trxSeq).padStart(3, '0');

  // ----- totals -----
  const subtotal = cart.reduce((s, l) => s + l.lineTotal, 0);
  const discAmt = !discount ? 0
    : discount.type === 'pct' ? Math.round(subtotal * discount.val / 100)
    : Math.min(discount.val, subtotal);
  const taxedBase = Math.max(0, subtotal - discAmt);
  const tax = Math.round(taxedBase * POS_TAX_RATE);
  const total = taxedBase + tax;
  const discLabel = !discount ? '' : discount.type === 'pct' ? discount.val + '%' : rp(discount.val);

  const cartQtyByItem = React.useMemo(() => {
    const m = {};
    cart.forEach((l) => { m[l.item.item_pk] = (m[l.item.item_pk] || 0) + l.qty; });
    return m;
  }, [cart]);

  // ----- cart ops -----
  function mergeOrAdd(line) {
    setCart((prev) => {
      const idx = prev.findIndex((l) => l.sig === line.sig);
      if (idx >= 0) {
        const copy = [...prev];
        const ex = copy[idx];
        copy[idx] = { ...ex, qty: ex.qty + line.qty, lineTotal: ex.unitPrice * (ex.qty + line.qty) };
        return copy;
      }
      return [line, ...prev];
    });
  }
  function tapItem(item) {
    if (item.modifier_groups && item.modifier_groups.length > 0) {
      setModPanel({ open: true, item, isEdit: false, lineId: null, selections: defaultSelections(item), qty: 1 });
    } else {
      mergeOrAdd(buildLine(item, {}, 1));
      showToast(item.name + ' ditambahkan', I.check);
    }
  }
  function inc(id) { setCart((p) => p.map((l) => l.lineId === id ? { ...l, qty: l.qty + 1, lineTotal: l.unitPrice * (l.qty + 1) } : l)); }
  function dec(id) { setCart((p) => p.flatMap((l) => l.lineId !== id ? [l] : (l.qty <= 1 ? [] : [{ ...l, qty: l.qty - 1, lineTotal: l.unitPrice * (l.qty - 1) }]))); }
  function remove(id) { setCart((p) => p.filter((l) => l.lineId !== id)); }
  function editLine(line) {
    setModPanel({ open: true, item: line.item, isEdit: true, lineId: line.lineId, selections: deepSel(line.selections), qty: line.qty });
  }

  // ----- modifier panel ops -----
  function toggleOpt(group, option) {
    setModPanel((mp) => {
      const single = (group.max_selections === 1) || (group.max === 1);
      const cur = mp.selections[group.pk] || [];
      let next;
      if (single) {
        next = [option.pk];
      } else {
        const max = group.max || group.max_selections || 99;
        if (cur.includes(option.pk)) next = cur.filter((x) => x !== option.pk);
        else next = cur.length >= max ? cur : [...cur, option.pk];
      }
      return { ...mp, selections: { ...mp.selections, [group.pk]: next } };
    });
  }
  const modUnit = modPanel.item ? unitPrice(modPanel.item, modPanel.selections) : 0;
  function confirmMod() {
    const line = buildLine(modPanel.item, modPanel.selections, modPanel.qty);
    if (modPanel.isEdit) {
      setCart((p) => p.map((l) => l.lineId === modPanel.lineId ? { ...line, lineId: l.lineId } : l));
    } else {
      mergeOrAdd(line);
      showToast(modPanel.item.name + ' ditambahkan', I.check);
    }
    setModPanel((mp) => ({ ...mp, open: false }));
  }

  // ----- discount -----
  function applyDiscount(d) { setDiscount(d); setDiscOpen(false); if (d) showToast('Diskon ' + (d.type === 'pct' ? d.val + '%' : rp(d.val)) + ' diterapkan', I.tag); }

  // ----- hold / void -----
  function holdBill() {
    if (!cart.length) return;
    const snap = cart.map((l) => ({ ...l }));
    const entry = {
      id: 'HOLD-' + Date.now().toString().slice(-4),
      label: 'Pesanan ' + fmtTime(),
      time: fmtTime(),
      count: cart.reduce((s, l) => s + l.qty, 0),
      total, cart: snap,
    };
    setHeld((h) => [entry, ...h]);
    resetSale(false);
    showToast('Pesanan ditahan', I.pause);
  }
  function resumeHeld(h) {
    setCart(h.cart.map((l) => ({ ...l, lineId: 'L' + Math.random().toString(36).slice(2, 9) })));
    setHeld((list) => list.filter((x) => x.id !== h.id));
    setDiscount(null);
    setHeldOpen(false);
    showToast('Pesanan dilanjutkan', I.check);
  }
  function deleteHeld(id) { setHeld((list) => list.filter((x) => x.id !== id)); }
  function voidBill() { if (!cart.length) return; resetSale(false); showToast('Pesanan dibatalkan', I.ban); }

  function resetSale(bump) {
    setCart([]); setDiscount(null); setTender('cash');
    if (bump) setTrxSeq((s) => s + 1);
  }

  // ----- pay -----
  function onPay() {
    if (!cart.length) return;
    if (tender === 'cash') { setNumpad({ open: true, value: '' }); }
    else finalize(tender, total, 0);
  }
  function confirmCash(num) {
    setNumpad({ open: false, value: '' });
    finalize('cash', num, num - total);
  }
  function finalize(method, paid, change) {
    setSuccess({ open: true, data: { trxId, total, paid, change, method } });
  }
  function newSale() {
    setSuccess({ open: false, data: null });
    resetSale(true);
  }

  const themeRef = React.useRef(null);

  return (
    <React.Fragment>
      <div id="scaler" ref={(el) => fitScale(el)}>
        <div className="tablet" data-theme={t.theme} data-density={t.density} data-card={t.cardStyle} ref={themeRef}>
          <Catalog
            store={POS_STORE}
            items={POS_ITEMS}
            categories={POS_CATEGORIES}
            query={query} setQuery={setQuery}
            activeCat={activeCat} setActiveCat={setActiveCat}
            cardStyle={t.cardStyle}
            onTapItem={tapItem}
            cartQtyByItem={cartQtyByItem}
            heldCount={held.length}
            onOpenHeld={() => setHeldOpen(true)}
            now={now}
          />
          <Ticket
            trxId={trxId} cart={cart}
            subtotal={subtotal} taxRate={POS_TAX_RATE} tax={tax}
            discount={discAmt} discountLabel={discLabel} total={total}
            tender={tender} setTender={setTender}
            onInc={inc} onDec={dec} onRemove={remove} onEditLine={editLine}
            onVoid={voidBill} onHold={holdBill}
            onOpenDiscount={() => setDiscOpen(true)} onPay={onPay}
          />

          <Numpad
            open={numpad.open} total={total} value={numpad.value}
            setValue={(v) => setNumpad((n) => ({ ...n, value: v }))}
            onClose={() => setNumpad({ open: false, value: '' })}
            onConfirm={confirmCash}
          />
          <ModifierPanel
            open={modPanel.open} item={modPanel.item} isEdit={modPanel.isEdit}
            selections={modPanel.selections} qty={modPanel.qty}
            onToggle={toggleOpt} setQty={(q) => setModPanel((mp) => ({ ...mp, qty: q }))}
            lineTotal={modUnit * modPanel.qty}
            onClose={() => setModPanel((mp) => ({ ...mp, open: false }))}
            onConfirm={confirmMod}
          />
          <HeldPanel
            open={heldOpen} held={held}
            onClose={() => setHeldOpen(false)}
            onResume={resumeHeld} onDelete={deleteHeld}
          />
          <DiscountPanel
            open={discOpen} subtotal={subtotal} current={discount}
            onClose={() => setDiscOpen(false)} onApply={applyDiscount}
          />
          <SuccessOverlay open={success.open} data={success.data} onNew={newSale} onPrint={() => showToast('Struk dicetak', I.receipt)} />
          <Toast msg={toast.msg} Ico={toast.Ico} />
        </div>
      </div>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Tema warna" />
        <TweakRadio label="Tema" value={t.theme}
          options={['warm', 'cool', 'fresh']}
          onChange={(v) => setTweak('theme', v)} />
        <TweakSection label="Tata letak" />
        <TweakRadio label="Kepadatan" value={t.density}
          options={['comfy', 'compact']}
          onChange={(v) => setTweak('density', v)} />
        <TweakRadio label="Kartu produk" value={t.cardStyle}
          options={['block', 'photo', 'minimal']}
          onChange={(v) => setTweak('cardStyle', v)} />
      </TweaksPanel>
    </React.Fragment>
  );
}

function deepSel(sel) {
  const o = {};
  Object.keys(sel).forEach((k) => { o[k] = [...sel[k]]; });
  return o;
}
function fmtTime() {
  const d = new Date();
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}
let _fitBound = false;
function fitScale(el) {
  if (!el) return;
  const apply = () => {
    const s = Math.min(window.innerWidth / 1366, window.innerHeight / 1024);
    el.style.transform = 'scale(' + s + ')';
  };
  apply();
  if (!_fitBound) { _fitBound = true; window.addEventListener('resize', apply); }
  // keep a ref to re-apply
  window.__fit = apply;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
