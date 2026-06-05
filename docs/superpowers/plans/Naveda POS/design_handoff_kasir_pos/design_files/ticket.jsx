// Order ticket (right): line items, totals, tenders, pay/void/hold + slide-up numpad
function Ticket({ trxId, cart, subtotal, taxRate, tax, discount, discountLabel, total,
                  tender, setTender, onInc, onDec, onRemove, onEditLine,
                  onVoid, onHold, onOpenDiscount, onPay, onOpenNumpad }) {
  const empty = cart.length === 0;
  const totalQty = cart.reduce((s, l) => s + l.qty, 0);

  return (
    <div className="ticket">
      <div className="tk-head">
        <div className="tk-title">
          <div className="lbl">Pesanan</div>
          <div className="trx">{trxId}</div>
        </div>
        <div className="tk-count"><I.cart size={16} />{totalQty} item</div>
      </div>

      {empty ? (
        <div className="cart-empty">
          <div className="ce-ic"><I.cart size={34} /></div>
          <div className="ce-t">Belum ada pesanan</div>
          <div className="ce-s">Ketuk produk di sebelah kiri untuk menambahkannya ke pesanan.</div>
        </div>
      ) : (
        <div className="tk-items thin-scroll">
          {cart.map((line) => (
            <LineItem
              key={line.lineId}
              line={line}
              onInc={() => onInc(line.lineId)}
              onDec={() => onDec(line.lineId)}
              onRemove={() => onRemove(line.lineId)}
              onEdit={() => onEditLine(line)}
            />
          ))}
        </div>
      )}

      <div className="tk-foot">
        <div className="totrow">
          <span className="k">Subtotal</span>
          <span className="v tnum">{rp(subtotal)}</span>
        </div>
        <div className="totrow">
          <span className="k">PPN {Math.round(taxRate * 100)}%</span>
          <span className="v tnum">{rp(tax)}</span>
        </div>
        {discount > 0 ? (
          <div className="totrow disc">
            <button className="disc-add" onClick={onOpenDiscount}>
              <I.tag size={15} />Diskon {discountLabel}
            </button>
            <span className="v tnum">−{rp(discount)}</span>
          </div>
        ) : (
          <div className="totrow">
            <button className="disc-add" onClick={onOpenDiscount} disabled={empty}
              style={empty ? { opacity: .4, cursor: 'not-allowed' } : null}>
              <I.tag size={15} />Tambah diskon
            </button>
            <span className="v" style={{ color: 'var(--ink-faint)' }}>—</span>
          </div>
        )}

        <div className="grand">
          <span className="gk">Total Bayar</span>
          <span className="gv tnum">{rp(total)}</span>
        </div>

        <div className="tenders">
          <Tender id="cash" label="Tunai" Ico={I.cash} sel={tender === 'cash'} onClick={() => setTender('cash')} />
          <Tender id="card" label="Kartu EDC" Ico={I.card} sel={tender === 'card'} onClick={() => setTender('card')} />
          <Tender id="qris" label="QRIS" Ico={I.qris} sel={tender === 'qris'} onClick={() => setTender('qris')} />
        </div>

        <button className="pay-btn" disabled={empty} onClick={onPay}>
          <span className="lead">
            <I.check3 size={26} />
            <span><small>Selesaikan</small><span className="big tnum">{rp(total)}</span></span>
          </span>
          <I.chevR size={28} />
        </button>

        <div className="sec-actions">
          <button className="sec-btn void" disabled={empty} onClick={onVoid}>
            <I.ban size={19} />Batalkan
          </button>
          <button className="sec-btn hold" disabled={empty} onClick={onHold}>
            <I.pause size={18} />Tahan
          </button>
        </div>
      </div>
    </div>
  );
}

function Tender({ label, Ico, sel, onClick }) {
  return (
    <button className={'tender' + (sel ? ' sel' : '')} onClick={onClick}>
      <span className="ti"><Ico size={22} /></span>
      {label}
    </button>
  );
}

function LineItem({ line, onInc, onDec, onRemove, onEdit }) {
  const { item, qty, modLabels, lineTotal } = line;
  const editable = item.modifier_groups && item.modifier_groups.length > 0;
  return (
    <div className="line">
      <div className="line-top">
        <div style={{ minWidth: 0 }}>
          <div className="line-name">{item.name}</div>
          {modLabels.length > 0 && (
            <div className="line-mods">
              {modLabels.map((m, i) => (
                <span key={i}>{m.add ? <>{m.name} <b>+{rp(m.add)}</b></> : m.name}</span>
              ))}
            </div>
          )}
        </div>
        <div className="line-price tnum">{rp(lineTotal)}</div>
      </div>
      <div className="line-bottom">
        <div className="stepper">
          <button className="minus" onClick={onDec}><I.minus size={20} /></button>
          <span className="qv tnum">{qty}</span>
          <button onClick={onInc}><I.plus size={20} /></button>
        </div>
        {editable && (
          <button className="line-edit" onClick={onEdit}><I.sliders size={15} />Ubah</button>
        )}
        <button className="line-trash" onClick={onRemove}><I.trash size={19} /></button>
      </div>
    </div>
  );
}

// ---- Slide-up numpad (cash entry / amount) ----
function Numpad({ open, total, value, setValue, onClose, onConfirm }) {
  const num = Number(value) || 0;
  const change = num - total;
  const press = (k) => {
    if (k === 'del') return setValue(value.slice(0, -1));
    if (k === '000') return setValue(value === '' ? '' : value + '000');
    setValue((value + k).replace(/^0+(?=\d)/, '').slice(0, 12));
  };
  const quick = (v) => setValue(String(v));
  return (
    <>
      <div className={'sheet-scrim' + (open ? ' on' : '')} onClick={onClose}></div>
      <div className={'numpad' + (open ? ' on' : '')}>
        <div className="np-head">
          <span className="np-t">Pembayaran Tunai</span>
          <button className="np-x" onClick={onClose}><I.close size={18} /></button>
        </div>
        <div className="np-display">
          <span className="np-lbl">Uang diterima</span>
          <span className="np-val tnum">{rp(num)}</span>
        </div>
        <div className="np-display" style={{ background: change >= 0 ? 'var(--pay-soft)' : 'var(--danger-soft)' }}>
          <span className="np-lbl" style={{ color: change >= 0 ? 'var(--pay-deep)' : 'var(--danger)' }}>
            {change >= 0 ? 'Kembalian' : 'Kurang'}
          </span>
          <span className="np-val tnum" style={{ color: change >= 0 ? 'var(--pay-deep)' : 'var(--danger)' }}>
            {rp(Math.abs(change))}
          </span>
        </div>
        <div className="np-quick">
          <button onClick={() => quick(total)}>Uang Pas</button>
          <button onClick={() => quick(Math.ceil(total / 50000) * 50000)}>{rp(Math.ceil(total / 50000) * 50000)}</button>
          <button onClick={() => quick(Math.ceil(total / 100000) * 100000)}>{rp(Math.ceil(total / 100000) * 100000)}</button>
        </div>
        <div className="np-keys">
          {['1','2','3','4','5','6','7','8','9'].map((k) => (
            <button key={k} onClick={() => press(k)}>{k}</button>
          ))}
          <button onClick={() => press('000')}>000</button>
          <button onClick={() => press('0')}>0</button>
          <button className="np-del" onClick={() => press('del')}><I.back size={22} /></button>
        </div>
        <button className="np-confirm pay" disabled={change < 0}
          style={change < 0 ? { opacity: .45, cursor: 'not-allowed' } : null}
          onClick={() => change >= 0 && onConfirm(num)}>
          Konfirmasi Pembayaran
        </button>
      </div>
    </>
  );
}

Object.assign(window, { Ticket, LineItem, Tender, Numpad });
