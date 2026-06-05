// Slide-in overlays: modifiers, held bills, discount + success state + toast

function ModifierPanel({ open, item, isEdit, selections, qty, onToggle, setQty,
                         lineTotal, onClose, onConfirm }) {
  if (!item) return null;
  const groups = item.modifier_groups || [];
  return (
    <>
      <div className={'ov-scrim' + (open ? ' on' : '')} onClick={onClose}></div>
      <div className={'overlay' + (open ? ' on' : '')}>
        <div className="ov-head">
          <button className="ov-x" onClick={onClose}><I.back size={22} /></button>
          <div className="ov-htxt">
            <div className="ov-t">{item.name}</div>
            <div className="ov-s">{rp(item.selling_price)} · pilih opsi di bawah</div>
          </div>
        </div>

        <div className="ov-body thin-scroll">
          {groups.map((g) => {
            const single = g.max_selections === 1 || g.max === 1;
            const sel = selections[g.pk] || [];
            return (
              <div className="mgroup" key={g.pk}>
                <div className="mgroup-head">
                  <span className="mg-name">{g.nama}</span>
                  {g.is_required
                    ? <span className="mg-rule req">Wajib</span>
                    : <span className="mg-rule opt">Opsional{(g.max > 1 || g.max_selections > 1) ? ` · maks ${g.max || g.max_selections}` : ''}</span>}
                </div>
                <div className="mopts">
                  {g.options.map((o) => {
                    const on = sel.includes(o.pk);
                    return (
                      <button key={o.pk} className={'mopt' + (on ? ' sel' : '')}
                        onClick={() => onToggle(g, o)}>
                        <span className="mo-check">{on && <I.check size={15} sw="3" />}</span>
                        <span className="mo-name">{o.name}</span>
                        {Number(o.additional_price) > 0 && (
                          <span className="mo-add">+{rp(o.additional_price)}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
          {groups.length === 0 && (
            <div style={{ color: 'var(--ink-faint)', fontWeight: 600 }}>Produk ini tidak punya opsi tambahan.</div>
          )}

          <div className="mgroup">
            <div className="mgroup-head"><span className="mg-name">Jumlah</span></div>
            <div className="mqty">
              <div className="stepper">
                <button className="minus" onClick={() => setQty(Math.max(1, qty - 1))}><I.minus size={20} /></button>
                <span className="qv tnum">{qty}</span>
                <button onClick={() => setQty(qty + 1)}><I.plus size={20} /></button>
              </div>
            </div>
          </div>
        </div>

        <div className="ov-foot">
          <button className="sec-btn hold" style={{ flex: '0 0 130px' }} onClick={onClose}>Batal</button>
          <button className="pay-btn" style={{ flex: 1, height: 56 }} onClick={onConfirm}>
            <span className="lead"><I.cart size={22} /><span className="big">{isEdit ? 'Simpan' : 'Tambah'}</span></span>
            <span className="amt tnum">{rp(lineTotal)}</span>
          </button>
        </div>
      </div>
    </>
  );
}

function HeldPanel({ open, held, onClose, onResume, onDelete }) {
  return (
    <>
      <div className={'ov-scrim' + (open ? ' on' : '')} onClick={onClose}></div>
      <div className={'overlay' + (open ? ' on' : '')}>
        <div className="ov-head">
          <button className="ov-x" onClick={onClose}><I.close size={22} /></button>
          <div className="ov-htxt">
            <div className="ov-t">Pesanan Tertahan</div>
            <div className="ov-s">{held.length} pesanan disimpan · ketuk untuk melanjutkan</div>
          </div>
        </div>
        <div className="ov-body thin-scroll">
          {held.length === 0 ? (
            <div style={{ color: 'var(--ink-faint)', fontWeight: 600, textAlign: 'center', padding: '40px 0' }}>
              Tidak ada pesanan tertahan.
            </div>
          ) : held.map((h) => (
            <div className="held-card" key={h.id}>
              <div className="hc-ic"><I.pause size={20} /></div>
              <div className="hc-meta">
                <div className="hc-l">{h.label}</div>
                <div className="hc-s">{h.count} item · {h.time}</div>
              </div>
              <div className="hc-total tnum">{rp(h.total)}</div>
              <button className="line-trash" onClick={() => onDelete(h.id)}><I.trash size={18} /></button>
              <button className="hc-resume" onClick={() => onResume(h)}>Lanjutkan</button>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function DiscountPanel({ open, subtotal, current, onClose, onApply }) {
  const pcts = [0, 5, 10, 15, 20, 25];
  const amts = [10000, 25000, 50000];
  const isPct = (v) => current && current.type === 'pct' && current.val === v;
  const isAmt = (v) => current && current.type === 'amt' && current.val === v;
  return (
    <>
      <div className={'ov-scrim' + (open ? ' on' : '')} onClick={onClose}></div>
      <div className={'overlay' + (open ? ' on' : '')} style={{ width: 460 }}>
        <div className="ov-head">
          <button className="ov-x" onClick={onClose}><I.close size={22} /></button>
          <div className="ov-htxt">
            <div className="ov-t">Diskon</div>
            <div className="ov-s">Diterapkan pada subtotal {rp(subtotal)}</div>
          </div>
        </div>
        <div className="ov-body thin-scroll">
          <div className="mgroup">
            <div className="mgroup-head"><span className="mg-name">Persentase</span></div>
            <div className="disc-grid">
              {pcts.map((p) => (
                <button key={p} className={'disc-opt' + (isPct(p) ? ' sel' : '')}
                  onClick={() => onApply(p === 0 ? null : { type: 'pct', val: p })}>
                  {p === 0 ? 'Tanpa' : p + '%'}
                </button>
              ))}
            </div>
          </div>
          <div className="mgroup">
            <div className="mgroup-head"><span className="mg-name">Nominal</span></div>
            <div className="disc-grid">
              {amts.map((a) => (
                <button key={a} className={'disc-opt' + (isAmt(a) ? ' sel' : '')}
                  style={{ fontSize: 15 }}
                  onClick={() => onApply({ type: 'amt', val: a })}>
                  {rp(a)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function SuccessOverlay({ open, data, onNew, onPrint }) {
  if (!data) return null;
  const methodLabel = { cash: 'Tunai', card: 'Kartu EDC', qris: 'QRIS' }[data.method] || 'Tunai';
  return (
    <div className={'success-scrim' + (open ? ' on' : '')}>
      <div className="success-card">
        <div className="success-ring"><I.check size={48} sw="3" /></div>
        <div className="success-t">Pembayaran Berhasil</div>
        <div className="success-s">Pesanan selesai diproses</div>
        <div className="success-amts">
          <div className="sa-row"><span className="k">Total</span><span className="v tnum">{rp(data.total)}</span></div>
          <div className="sa-row"><span className="k">Metode · {methodLabel}</span><span className="v tnum">{rp(data.paid)}</span></div>
          {data.method === 'cash' && (
            <div className="sa-row change"><span className="k">Kembalian</span><span className="v tnum">{rp(data.change)}</span></div>
          )}
        </div>
        <div className="trx-pill">{data.trxId}</div>
        <div className="success-actions">
          <button className="s-print" onClick={onPrint}><I.receipt size={20} style={{ verticalAlign: -4, marginRight: 8 }} />Cetak Struk</button>
          <button className="s-new" onClick={onNew}>Transaksi Baru</button>
        </div>
      </div>
    </div>
  );
}

function Toast({ msg, Ico }) {
  return (
    <div className={'toast' + (msg ? ' on' : '')}>
      {Ico && <Ico size={18} />}{msg}
    </div>
  );
}

Object.assign(window, { ModifierPanel, HeldPanel, DiscountPanel, SuccessOverlay, Toast });
