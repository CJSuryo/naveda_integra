# PSAK 71 Amortised Cost – Piutang Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the piutang app from SAK ETAP gross method (separate Pendapatan Bunga Ditangguhkan contra-account) to PSAK 71 amortised cost, where the piutang account balance IS the carrying amount and no deferred income account is used.

**Architecture:** At initial recognition, debit piutang at fair value (PV); credit revenue at PV — no deferred contra entry. Periodic EIR journals debit piutang directly (increasing carrying amount). Payments credit piutang for the full contractual cash flow. Reklasifikasi transfers the carrying-amount portion (nominal − net EIR) between LT and current accounts as a single pair of entries. All carrying value reads are derived from the net piutang account balance across all related journals.

**Tech Stack:** Django ORM, Python Decimal, `apps/piutang/services.py` (primary), `apps/piutang/tests.py` (tests). No model migrations needed — `deferred_income_account` and `deferred_income_lancar_account` fields are kept in the model but left unused by new journal logic.

---

## File Map

| File | What changes |
|------|--------------|
| `apps/piutang/services.py` | All accounting logic — 9 function changes, 2 deletions |
| `apps/piutang/views.py` | `piutang_reklasifikasi_bagian_lancar` & `piutang_set_akun_lancar` — remove deferred account passing; detail view — remove `pv_unamortized_deferred` context |
| `apps/piutang/tests.py` | Add PSAK 71 posting, EIR amortization, payment, and reklasifikasi tests |

---

## Task 1: Add `bunga_efektif_gross` to amortization schedule

**Files:**
- Modify: `apps/piutang/services.py:2021-2027`
- Test: `apps/piutang/tests.py`

`compute_amortization_schedule_pv` currently stores only `bunga_efektif` (net = EIR − coupon). Under PSAK 71 the periodic EIR journal uses the **gross** EIR. Add `bunga_efektif_gross` to each row.

- [ ] **Step 1: Write failing test**

Add to `apps/piutang/tests.py` at the end of `ComputeAmortizationSchedulePvTest`:

```python
def test_schedule_has_bunga_efektif_gross(self):
    f = make_fixtures()
    p = create_manual_piutang(
        tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
        coa_piutang_account=f['coa_piutang'],
        jatuh_tempo=date(2028, 1, 1),
        jenis_jangka_waktu='long_term',
        details=[{'deskripsi': 'X', 'jumlah': Decimal('12000000')}],
    )
    p.nilai_wajar_awal = compute_present_value(p, Decimal('12'))
    p.pv_discount_rate = Decimal('12')
    rows = compute_amortization_schedule_pv(p)
    self.assertTrue(len(rows) > 0)
    for row in rows:
        self.assertIn('bunga_efektif_gross', row)
        self.assertGreaterEqual(row['bunga_efektif_gross'], Decimal('0'))
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.ComputeAmortizationSchedulePvTest.test_schedule_has_bunga_efektif_gross
```

Expected: FAIL with KeyError or AssertionError.

- [ ] **Step 3: Implement**

In `apps/piutang/services.py`, replace lines 2021-2027 (the `rows.append(...)` inside `compute_amortization_schedule_pv`):

```python
        rows.append({
            'periode': row['no'],
            'tanggal': row['tanggal'],
            'bunga_efektif': Decimal(str(round(net_amortization, 4))),
            'bunga_efektif_gross': Decimal(str(round(bunga_efektif_gross, 4))),
            'cash_flow': row['angsuran'],
            'carrying_value': Decimal(str(round(carrying, 4))),
        })
```

- [ ] **Step 4: Run test to confirm it passes**

```
python manage.py test apps.piutang.tests.ComputeAmortizationSchedulePvTest
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add bunga_efektif_gross to PV amortization schedule for PSAK 71"
```

---

## Task 2: Change initial AR posting journal to PSAK 71

**Files:**
- Modify: `apps/piutang/services.py:1863-1934` (`_create_piutang_ar_journal`)
- Test: `apps/piutang/tests.py`

**SAK ETAP (old):** `Dr. Piutang (face) / Cr. Revenue (PV) + Cr. Deferred Income (face − PV)`
**PSAK 71 (new):** `Dr. Piutang (PV) / Cr. Revenue (PV)` — no deferred income line.

- [ ] **Step 1: Write failing test**

Add to `apps/piutang/tests.py`:

```python
class PostPiutangPSAK71Test(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.coa_rev = Akun.objects.create(
            kategori_id='pendapatan', nama='Pendapatan PSAK71', kode_akun='4.1.71',
        )
        self.coa_deferred = Akun.objects.create(
            kategori_id='kewajiban', nama='Pend. Bunga Ditangguhkan', kode_akun='1.3.5',
        )
        self.coa_income = Akun.objects.create(
            kategori_id='pendapatan', nama='Pendapatan Bunga Efektif', kode_akun='4.2.1',
        )

    def _make_pv_piutang(self):
        from apps.piutang.services import post_piutang
        p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2028, 1, 1),
            jenis_jangka_waktu='long_term',
            pv_discount_rate=Decimal('12'),
            deferred_income_account=self.coa_deferred,
            interest_income_account=self.coa_income,
            details=[{
                'deskripsi': 'X', 'jumlah': Decimal('12000000'),
                'revenue_account': self.coa_rev,
            }],
        )
        post_piutang(p)
        p.refresh_from_db()
        return p

    def test_posting_debits_piutang_at_fair_value_not_face(self):
        from apps.jurnal.models import JurnalDetail
        p = self._make_pv_piutang()
        pv = p.nilai_wajar_awal
        # The initial posting journal should debit piutang at PV, not 12_000_000
        debit_lines = JurnalDetail.objects.filter(
            akun=self.f['coa_piutang'], debit__gt=0
        )
        self.assertEqual(debit_lines.count(), 1)
        self.assertAlmostEqual(float(debit_lines.first().debit), float(pv), places=0)
        self.assertLess(debit_lines.first().debit, Decimal('12000000'))

    def test_posting_does_not_create_deferred_income_credit(self):
        from apps.jurnal.models import JurnalDetail
        p = self._make_pv_piutang()
        deferred_credits = JurnalDetail.objects.filter(
            akun=self.coa_deferred, kredit__gt=0
        )
        self.assertEqual(deferred_credits.count(), 0)

    def test_posting_journal_is_balanced(self):
        from apps.jurnal.models import JurnalDetail, JurnalHeader
        p = self._make_pv_piutang()
        journal = JurnalHeader.objects.filter(
            uraian_transaksi__startswith=f'Pengakuan Piutang {p.nomor_piutang}'
        ).first()
        self.assertIsNotNone(journal)
        total_debit = sum(d.debit for d in journal.details.all())
        total_kredit = sum(d.kredit for d in journal.details.all())
        self.assertAlmostEqual(float(total_debit), float(total_kredit), places=2)
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.PostPiutangPSAK71Test
```

Expected: `test_posting_debits_piutang_at_fair_value_not_face` fails (debit is 12_000_000, not PV), `test_posting_does_not_create_deferred_income_credit` fails (deferred credit exists).

- [ ] **Step 3: Implement**

In `apps/piutang/services.py`, replace `_create_piutang_ar_journal` (lines 1863-1934) with:

```python
def _create_piutang_ar_journal(piutang: PiutangHeader) -> JurnalHeader:
    details = list(piutang.details.select_related('revenue_account').all())
    missing = [d.deskripsi or str(d.pk) for d in details if not d.revenue_account_id]
    if missing:
        raise ValueError(
            f'Akun pendapatan belum diisi untuk detail: {", ".join(missing)}. '
            'Isi akun pendapatan di setiap baris detail sebelum posting.'
        )
    nomor = _next_piutang_journal_number('TRX-PIU-POST')
    header = JurnalHeader.objects.create(
        tanggal=piutang.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Pengakuan Piutang {piutang.nomor_piutang}',
        entitas_bisnis=piutang.entitas_bisnis,
        is_penyesuaian=False,
    )

    if piutang.is_pv_adjusted and piutang.nilai_wajar_awal:
        # PSAK 71 amortised cost: Dr. Piutang at fair value / Cr. Revenue at fair value.
        # No deferred income — the discount is implicit in the carrying amount.
        pv = piutang.nilai_wajar_awal
        JurnalDetail.objects.create(
            jurnal_header=header,
            akun=piutang.coa_piutang_account,
            debit=pv,
            kredit=Decimal('0'),
        )
        total_detail = sum(d.jumlah for d in details) or pv
        cumulative = Decimal('0')
        detail_entries = []
        for i, detail in enumerate(details):
            if i == len(details) - 1:
                kredit = pv - cumulative
            else:
                kredit = (detail.jumlah / total_detail * pv).quantize(Decimal('0.0001'))
            cumulative += kredit
            detail_entries.append(JurnalDetail(
                jurnal_header=header,
                akun=detail.revenue_account,
                debit=Decimal('0'),
                kredit=kredit,
            ))
        JurnalDetail.objects.bulk_create(detail_entries)
    else:
        # Standard method: Dr. Piutang (face) / Cr. Revenue (face)
        JurnalDetail.objects.create(
            jurnal_header=header,
            akun=piutang.coa_piutang_account,
            debit=piutang.jumlah_pokok,
            kredit=Decimal('0'),
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=detail.revenue_account,
                debit=Decimal('0'),
                kredit=detail.jumlah,
            )
            for detail in details
        ])
    return header
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.piutang.tests.PostPiutangPSAK71Test apps.piutang.tests.PostPiutangTest
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): PSAK 71 initial recognition at fair value, no deferred income"
```

---

## Task 3: Rewrite `_pv_carrying_value` to read account balance

**Files:**
- Modify: `apps/piutang/services.py:1707-1797` (replace `_pv_net_amortized`, `_pv_pokok_paid`, `_pv_carrying_value`)
- Test: `apps/piutang/tests.py`

Under PSAK 71 the carrying amount equals the net debit balance of the piutang account across all its journals. The old formula (`nilai_wajar_awal + amortized − pokok_paid`) no longer applies because EIR journals now debit piutang (not deferred), and payments credit piutang for the full cash flow.

**New formula:** `carrying = Σ(debits on coa_piutang + coa_piutang_lancar) − Σ(credits on those accounts)` across `_piutang_journal_ids`.

- [ ] **Step 1: Write failing test**

Add to `apps/piutang/tests.py`:

```python
class PvCarryingValuePSAK71Test(TestCase):
    """Under PSAK 71, carrying value = net debit on piutang accounts from all journals."""

    def setUp(self):
        self.f = make_fixtures()
        self.coa_rev = Akun.objects.create(
            kategori_id='pendapatan', nama='Pend PSAK71 CV', kode_akun='4.1.72',
        )
        self.coa_deferred = Akun.objects.create(
            kategori_id='kewajiban', nama='PBD CV', kode_akun='1.3.51',
        )
        self.coa_income = Akun.objects.create(
            kategori_id='pendapatan', nama='PBE CV', kode_akun='4.2.11',
        )

    def _posted_pv_piutang(self):
        from apps.piutang.services import post_piutang
        p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2028, 1, 1),
            jenis_jangka_waktu='long_term',
            pv_discount_rate=Decimal('12'),
            deferred_income_account=self.coa_deferred,
            interest_income_account=self.coa_income,
            details=[{
                'deskripsi': 'X', 'jumlah': Decimal('12000000'),
                'revenue_account': self.coa_rev,
            }],
        )
        post_piutang(p)
        p.refresh_from_db()
        return p

    def test_carrying_value_equals_pv_immediately_after_posting(self):
        from apps.piutang.services import _pv_carrying_value
        p = self._posted_pv_piutang()
        cv = _pv_carrying_value(p)
        self.assertAlmostEqual(float(cv), float(p.nilai_wajar_awal), places=0)

    def test_carrying_value_reduces_after_payment(self):
        from apps.piutang.services import _pv_carrying_value
        p = self._posted_pv_piutang()
        cv_before = _pv_carrying_value(p)
        create_piutang_payment(
            p,
            {'tanggal_terima': date(2026, 2, 1), 'jumlah_diterima': Decimal('500000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        p.refresh_from_db()
        cv_after = _pv_carrying_value(p)
        self.assertLess(cv_after, cv_before)
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.PvCarryingValuePSAK71Test
```

Expected: Fails because carrying value after payment still uses old formula.

- [ ] **Step 3: Implement**

In `apps/piutang/services.py`, replace the three helper functions `_pv_net_amortized` (lines 1707-1732), `_pv_pokok_paid` (lines 1754-1781), and `_pv_carrying_value` (lines 1784-1797) with just one function:

```python
def _pv_carrying_value(piutang: PiutangHeader) -> Decimal:
    """
    PSAK 71: carrying amount = net debit balance of piutang accounts across all journals.
    Includes both coa_piutang_account (LT) and coa_piutang_lancar_account (current) so
    reklasifikasi transfers (which shift balance between the two) are transparent.
    """
    if not piutang.is_pv_adjusted or not piutang.nilai_wajar_awal:
        return piutang.sisa_piutang
    account_ids = [piutang.coa_piutang_account_id]
    if piutang.coa_piutang_lancar_account_id:
        account_ids.append(piutang.coa_piutang_lancar_account_id)
    journal_ids = _piutang_journal_ids(piutang)
    if not journal_ids:
        return piutang.nilai_wajar_awal
    result = (
        JurnalDetail.objects
        .filter(akun_id__in=account_ids, jurnal_header_id__in=journal_ids)
        .aggregate(debit=Sum('debit'), kredit=Sum('kredit'))
    )
    net = (result['debit'] or Decimal('0')) - (result['kredit'] or Decimal('0'))
    return max(Decimal('0'), net.quantize(Decimal('0.0001')))
```

Also search for and remove/replace any remaining references to `_pv_net_amortized` and `_pv_pokok_paid` in `views.py`. In `views.py` around line 433, replace:

```python
        'pv_unamortized_deferred': (
            (piutang.jumlah_pokok - piutang.nilai_wajar_awal) - _pv_net_amortized(piutang)
        ) if (piutang.is_pv_adjusted and piutang.nilai_wajar_awal) else None,
```

with:

```python
        'pv_unamortized_deferred': None,
```

(Under PSAK 71 there is no deferred balance — the carrying amount subsumes it.)

And remove the import of `_pv_net_amortized` from `views.py` line ~34 if it exists there.

- [ ] **Step 4: Run tests**

```
python manage.py test apps.piutang.tests.PvCarryingValuePSAK71Test apps.piutang.tests.PostPiutangPSAK71Test
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/views.py apps/piutang/tests.py
git commit -m "feat(piutang): PSAK 71 carrying value reads piutang account balance directly"
```

---

## Task 4: Update EIR amortization journal (`create_pv_adjustment_journal`)

**Files:**
- Modify: `apps/piutang/services.py:2031-2152`
- Test: `apps/piutang/tests.py`

**SAK ETAP (old):** `Dr. Pendapatan Bunga Ditangguhkan (net = EIR − coupon) / Cr. Pendapatan Bunga Efektif`
**PSAK 71 (new):** `Dr. Piutang (gross EIR = carrying × rate) / Cr. Pendapatan Bunga Efektif`

Uses `row['bunga_efektif_gross']` from Task 1. `bunga_efektif_gross` ≥ 0 always, so the negative re-deferral branch is eliminated.

- [ ] **Step 1: Write failing test**

Add to `apps/piutang/tests.py`:

```python
class PvAdjustmentJournalPSAK71Test(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.coa_rev = Akun.objects.create(
            kategori_id='pendapatan', nama='Pend Adj', kode_akun='4.1.73',
        )
        self.coa_deferred = Akun.objects.create(
            kategori_id='kewajiban', nama='PBD Adj', kode_akun='1.3.52',
        )
        self.coa_income = Akun.objects.create(
            kategori_id='pendapatan', nama='PBE Adj', kode_akun='4.2.12',
        )
        from apps.piutang.services import post_piutang
        self.p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2028, 1, 1),
            jenis_jangka_waktu='long_term',
            pv_discount_rate=Decimal('12'),
            deferred_income_account=self.coa_deferred,
            interest_income_account=self.coa_income,
            details=[{
                'deskripsi': 'X', 'jumlah': Decimal('12000000'),
                'revenue_account': self.coa_rev,
            }],
        )
        post_piutang(self.p)
        self.p.refresh_from_db()

    def test_amortization_journal_debits_piutang_not_deferred(self):
        from apps.piutang.services import create_pv_adjustment_journal
        from apps.jurnal.models import JurnalDetail
        create_pv_adjustment_journal(
            piutang=self.p,
            interest_income_account=self.coa_income,
            tanggal=date(2026, 2, 1),
            periode_no=1,
        )
        # Should have Dr. Piutang / Cr. Income — no deferred account
        deferred_hits = JurnalDetail.objects.filter(akun=self.coa_deferred)
        self.assertEqual(deferred_hits.count(), 0)
        piutang_debits = JurnalDetail.objects.filter(
            akun=self.f['coa_piutang'], debit__gt=0
        ).exclude(
            jurnal_header__uraian_transaksi__startswith='Pengakuan'
        )
        self.assertGreater(piutang_debits.count(), 0)

    def test_amortization_journal_is_balanced(self):
        from apps.piutang.services import create_pv_adjustment_journal
        journal = create_pv_adjustment_journal(
            piutang=self.p,
            interest_income_account=self.coa_income,
            tanggal=date(2026, 2, 1),
            periode_no=1,
        )
        total_debit = sum(d.debit for d in journal.details.all())
        total_kredit = sum(d.kredit for d in journal.details.all())
        self.assertAlmostEqual(float(total_debit), float(total_kredit), places=2)
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.PvAdjustmentJournalPSAK71Test
```

Expected: Fails — deferred account is hit, piutang is not debited.

- [ ] **Step 3: Implement**

Replace `create_pv_adjustment_journal` in `apps/piutang/services.py` (lines 2031-2152):

```python
def create_pv_adjustment_journal(
    piutang: PiutangHeader,
    interest_income_account,
    tanggal,
    catatan='',
    user=None,
    periode_no: int | None = None,
) -> JurnalHeader:
    """PSAK 71: Dr. Piutang (gross EIR) / Cr. Pendapatan Bunga Efektif."""
    if not piutang.is_pv_adjusted or not piutang.nilai_wajar_awal or not piutang.pv_discount_rate:
        raise ValueError('Piutang belum disesuaikan nilai wajar (PV).')
    amort = compute_amortization_schedule_pv(piutang)
    if not amort:
        raise ValueError('Jadwal amortisasi PV tidak tersedia.')

    if periode_no is None:
        prefix_pattern = f'Amortisasi PV Piutang {piutang.nomor_piutang}'
        recorded = JurnalHeader.objects.filter(
            uraian_transaksi__startswith=prefix_pattern,
        ).count()
        periode_no = recorded + 1

    if periode_no < 1 or periode_no > len(amort):
        raise ValueError(f'Periode {periode_no} tidak valid (total {len(amort)} periode).')

    row = amort[periode_no - 1]
    bunga = row['bunga_efektif_gross']
    if bunga <= Decimal('0.005'):
        raise ValueError('Bunga efektif nol, tidak perlu jurnal.')

    # Use current-portion account if reklasifikasi has been done, else LT account.
    ar_account = (
        piutang.coa_piutang_lancar_account
        if piutang.coa_piutang_lancar_account_id
        else piutang.coa_piutang_account
    )
    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-PV')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Amortisasi PV Piutang {piutang.nomor_piutang} — Periode {periode_no}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=ar_account,
                debit=bunga,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=interest_income_account,
                debit=Decimal('0'),
                kredit=bunga,
            ),
        ])
        _log(
            piutang, 'EDITED', user=user,
            after={'pv_amortisasi': str(bunga), 'periode': periode_no},
        )
    return header
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.piutang.tests.PvAdjustmentJournalPSAK71Test
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): PSAK 71 EIR amortization debits piutang account (not deferred)"
```

---

## Task 5: Update EIR accrual journal (`create_pv_accrual_journal`)

**Files:**
- Modify: `apps/piutang/services.py:2155-2266`
- Test: `apps/piutang/tests.py`

**SAK ETAP (old):** `Dr. Deferred (net) / Cr. Income`
**PSAK 71 (new):** `Dr. Piutang (gross EIR for days elapsed) / Cr. Pendapatan Bunga Efektif`

`_pv_effective_interest_days` already returns the gross EIR. Remove `_contractual_interest_in_period` call and the negative-bunga branch.

- [ ] **Step 1: Write failing test**

Add to `apps/piutang/tests.py`:

```python
class PvAccrualJournalPSAK71Test(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.coa_rev = Akun.objects.create(
            kategori_id='pendapatan', nama='Pend Akrual', kode_akun='4.1.74',
        )
        self.coa_deferred = Akun.objects.create(
            kategori_id='kewajiban', nama='PBD Akrual', kode_akun='1.3.53',
        )
        self.coa_income = Akun.objects.create(
            kategori_id='pendapatan', nama='PBE Akrual', kode_akun='4.2.13',
        )
        from apps.piutang.services import post_piutang
        self.p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2028, 1, 1),
            jenis_jangka_waktu='long_term',
            pv_discount_rate=Decimal('12'),
            deferred_income_account=self.coa_deferred,
            interest_income_account=self.coa_income,
            details=[{
                'deskripsi': 'X', 'jumlah': Decimal('12000000'),
                'revenue_account': self.coa_rev,
            }],
        )
        post_piutang(self.p)
        self.p.refresh_from_db()

    def test_accrual_debits_piutang_not_deferred(self):
        from apps.piutang.services import create_pv_accrual_journal
        from apps.jurnal.models import JurnalDetail
        create_pv_accrual_journal(
            piutang=self.p,
            tanggal=date(2026, 3, 31),
            interest_income_account=self.coa_income,
        )
        deferred_hits = JurnalDetail.objects.filter(akun=self.coa_deferred)
        self.assertEqual(deferred_hits.count(), 0)
        # Piutang should have a non-posting debit (accrual)
        piutang_debits = JurnalDetail.objects.filter(
            akun=self.f['coa_piutang'], debit__gt=0,
            jurnal_header__is_penyesuaian=True,
        )
        self.assertGreater(piutang_debits.count(), 0)

    def test_accrual_journal_is_balanced(self):
        from apps.piutang.services import create_pv_accrual_journal
        j = create_pv_accrual_journal(
            piutang=self.p,
            tanggal=date(2026, 3, 31),
            interest_income_account=self.coa_income,
        )
        total_debit = sum(d.debit for d in j.details.all())
        total_kredit = sum(d.kredit for d in j.details.all())
        self.assertAlmostEqual(float(total_debit), float(total_kredit), places=2)
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.PvAccrualJournalPSAK71Test
```

Expected: Fails.

- [ ] **Step 3: Implement**

Replace `create_pv_accrual_journal` in `apps/piutang/services.py` (lines 2155-2266):

```python
def create_pv_accrual_journal(
    piutang: PiutangHeader,
    tanggal: date,
    interest_income_account=None,
    catatan: str = '',
    user=None,
) -> JurnalHeader:
    """
    PSAK 71: period-end accrual journal.
    Dr. Piutang (gross EIR for days elapsed) / Cr. Pendapatan Bunga Efektif.
    Must be paired with a reversal at start of next period.
    """
    if not piutang.is_pv_adjusted or not piutang.pv_discount_rate:
        raise ValueError('Piutang belum disesuaikan nilai wajar (PV).')
    income_account = interest_income_account or piutang.interest_income_account
    if not income_account:
        raise ValueError('Akun Pendapatan Bunga Efektif diperlukan.')

    from_date = _pv_last_amortization_date(piutang)
    bunga = _pv_effective_interest_days(piutang, from_date, tanggal)
    if bunga <= Decimal('0'):
        raise ValueError('Tidak ada selisih bunga efektif yang dapat diakrualkan untuk periode ini.')

    nom = piutang.nomor_piutang
    n_accrual = JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Akrual PV Piutang {nom} —'
    ).count()
    n_reversal = JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Balik Akrual PV Piutang {nom} —'
    ).count()
    if n_accrual > n_reversal:
        raise ValueError(
            'Masih ada jurnal akrual yang belum dibalik. Balik akrual sebelumnya terlebih dahulu.'
        )

    ar_account = (
        piutang.coa_piutang_lancar_account
        if piutang.coa_piutang_lancar_account_id
        else piutang.coa_piutang_account
    )
    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-PV')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Akrual PV Piutang {nom} — s.d. {tanggal}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=ar_account,
                debit=bunga,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=income_account,
                debit=Decimal('0'),
                kredit=bunga,
            ),
        ])
        _log(piutang, 'EDITED', user=user,
             after={'pv_akrual': str(bunga), 'tanggal': str(tanggal)})
    return header
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.piutang.tests.PvAccrualJournalPSAK71Test
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): PSAK 71 EIR accrual debits piutang account (gross EIR)"
```

---

## Task 6: Update payment journal for PSAK 71

**Files:**
- Modify: `apps/piutang/services.py:518-696` (`_create_payment_journal`)
- Test: `apps/piutang/tests.py`

Two changes for PV-adjusted piutang:

1. **Pre-payment EIR block** (lines 529-610): Change debit target from deferred accounts to the piutang account; use gross EIR (not net). Remove `_contractual_interest_in_period` call.

2. **Payment journal** (lines 612-696): For PV-adjusted piutang, credit piutang for the **full cash flow** (no angsuran split to income). Contractual interest income was already recognised via the EIR journal immediately above.

Non-PV-adjusted piutang keeps existing behaviour unchanged.

- [ ] **Step 1: Write failing test**

Add to `apps/piutang/tests.py`:

```python
class PaymentJournalPSAK71Test(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.coa_rev = Akun.objects.create(
            kategori_id='pendapatan', nama='Pend Pay', kode_akun='4.1.75',
        )
        self.coa_deferred = Akun.objects.create(
            kategori_id='kewajiban', nama='PBD Pay', kode_akun='1.3.54',
        )
        self.coa_income = Akun.objects.create(
            kategori_id='pendapatan', nama='PBE Pay', kode_akun='4.2.14',
        )
        from apps.piutang.services import post_piutang
        self.p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2027, 1, 1),
            jenis_jangka_waktu='long_term',
            pv_discount_rate=Decimal('12'),
            deferred_income_account=self.coa_deferred,
            interest_income_account=self.coa_income,
            details=[{
                'deskripsi': 'X', 'jumlah': Decimal('12000000'),
                'revenue_account': self.coa_rev,
            }],
        )
        post_piutang(self.p)
        self.p.refresh_from_db()

    def test_payment_credits_piutang_for_full_cash_flow(self):
        from apps.jurnal.models import JurnalDetail
        create_piutang_payment(
            self.p,
            {'tanggal_terima': date(2026, 2, 1), 'jumlah_diterima': Decimal('600000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        # Payment journal: Cr. Piutang should be 600_000 (full cash flow, not just principal)
        payment_credits = JurnalDetail.objects.filter(
            akun=self.f['coa_piutang'],
            kredit=Decimal('600000'),
            jurnal_header__uraian_transaksi__startswith='Penerimaan Piutang',
        )
        self.assertGreater(payment_credits.count(), 0)

    def test_payment_does_not_credit_deferred_account(self):
        from apps.jurnal.models import JurnalDetail
        create_piutang_payment(
            self.p,
            {'tanggal_terima': date(2026, 2, 1), 'jumlah_diterima': Decimal('600000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        deferred_hits = JurnalDetail.objects.filter(akun=self.coa_deferred)
        self.assertEqual(deferred_hits.count(), 0)

    def test_pre_payment_eir_journal_debits_piutang(self):
        """Pre-payment EIR should debit piutang (not deferred)."""
        from apps.jurnal.models import JurnalDetail
        create_piutang_payment(
            self.p,
            {'tanggal_terima': date(2026, 2, 1), 'jumlah_diterima': Decimal('600000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        eir_debits = JurnalDetail.objects.filter(
            akun=self.f['coa_piutang'],
            debit__gt=0,
            jurnal_header__uraian_transaksi__startswith='Amortisasi PV Piutang',
        )
        self.assertGreater(eir_debits.count(), 0)
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.PaymentJournalPSAK71Test
```

Expected: Fails.

- [ ] **Step 3: Implement**

Replace `_create_payment_journal` in `apps/piutang/services.py` (lines 518-696):

```python
def _create_payment_journal(piutang: PiutangHeader, penerimaan: PiutangPenerimaan) -> JurnalHeader:
    tanggal = penerimaan.tanggal_terima
    jumlah = penerimaan.jumlah_diterima

    # ── PSAK 71: Pre-payment EIR accrual ────────────────────────────────────────
    # Recognise gross effective interest from last amortisation to payment date.
    # Dr. Piutang / Cr. Pendapatan Bunga Efektif (increases carrying amount).
    if (piutang.is_pv_adjusted
            and piutang.interest_income_account_id
            and piutang.pv_discount_rate):
        from_date = _pv_last_amortization_date(piutang)
        bunga_efektif = _pv_effective_interest_days(piutang, from_date, tanggal)
        if abs(bunga_efektif) >= Decimal('0.005'):
            ar_account_eir = (
                piutang.coa_piutang_lancar_account
                if piutang.coa_piutang_lancar_account_id
                else piutang.coa_piutang_account
            )
            amort_nomor = _next_piutang_journal_number('TRX-PIU-PV')
            amort_header = JurnalHeader.objects.create(
                tanggal=tanggal,
                nomor_transaksi=amort_nomor,
                uraian_transaksi=(
                    f'Amortisasi PV Piutang {piutang.nomor_piutang} — '
                    f'{from_date} s.d. {tanggal}'
                ),
                entitas_bisnis=piutang.entitas_bisnis,
                is_penyesuaian=False,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(
                    jurnal_header=amort_header,
                    akun=ar_account_eir,
                    debit=bunga_efektif,
                    kredit=Decimal('0'),
                ),
                JurnalDetail(
                    jurnal_header=amort_header,
                    akun=piutang.interest_income_account,
                    debit=Decimal('0'),
                    kredit=bunga_efektif,
                ),
            ])

    # ── Payment journal ──────────────────────────────────────────────────────────
    # Determine which AR account to credit (current portion first after reklasifikasi).
    ar_account = (
        piutang.coa_piutang_lancar_account
        if piutang.coa_piutang_lancar_account_id
        else piutang.coa_piutang_account
    )
    nomor = _next_piutang_journal_number('TRX-PIU-P')
    header = JurnalHeader.objects.create(
        tanggal=tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Penerimaan Piutang {piutang.nomor_piutang} — {piutang.entitas_display}',
        entitas_bisnis=piutang.entitas_bisnis,
        is_penyesuaian=False,
    )

    if piutang.is_pv_adjusted and piutang.pv_discount_rate:
        # PSAK 71: full cash flow reduces carrying amount.
        # Contractual interest was already in the carrying amount via EIR; no split needed.
        if piutang.coa_piutang_lancar_account_id:
            bal_lancar = max(
                Decimal('0'),
                _net_debit_balance_for_piutang(piutang.coa_piutang_lancar_account, piutang),
            )
            credit_lancar = min(jumlah, bal_lancar)
            credit_lt = jumlah - credit_lancar
            payment_lines = [
                JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                             debit=jumlah, kredit=Decimal('0')),
            ]
            if credit_lancar > 0:
                payment_lines.append(JurnalDetail(
                    jurnal_header=header, akun=piutang.coa_piutang_lancar_account,
                    debit=Decimal('0'), kredit=credit_lancar,
                ))
            if credit_lt > 0:
                payment_lines.append(JurnalDetail(
                    jurnal_header=header, akun=piutang.coa_piutang_account,
                    debit=Decimal('0'), kredit=credit_lt,
                ))
            JurnalDetail.objects.bulk_create(payment_lines)
        else:
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                             debit=jumlah, kredit=Decimal('0')),
                JurnalDetail(jurnal_header=header, akun=ar_account,
                             debit=Decimal('0'), kredit=jumlah),
            ])
        return header

    # ── Non-PV-adjusted piutang: existing logic ──────────────────────────────────
    # For interest-bearing piutang with angsuran_no: split payment bunga dulu, sisanya pokok
    if (piutang.jenis_bunga != 'tanpa_bunga'
            and penerimaan.angsuran_no
            and piutang.interest_income_account_id):
        schedule = compute_angsuran_schedule(piutang)
        installment = next((r for r in schedule if r['no'] == penerimaan.angsuran_no), None)
        if installment:
            bunga_kontrak = installment['bunga']
            if jumlah >= installment['angsuran']:
                pokok_paid = installment['pokok']
                bunga_paid = bunga_kontrak
            elif jumlah >= bunga_kontrak:
                bunga_paid = bunga_kontrak
                pokok_paid = jumlah - bunga_kontrak
            else:
                bunga_paid = jumlah
                pokok_paid = Decimal('0')
            entries = [
                JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                             debit=jumlah, kredit=Decimal('0')),
            ]
            if pokok_paid > 0:
                entries.append(JurnalDetail(
                    jurnal_header=header, akun=ar_account,
                    debit=Decimal('0'), kredit=pokok_paid,
                ))
            if bunga_paid > 0:
                entries.append(JurnalDetail(
                    jurnal_header=header, akun=piutang.interest_income_account,
                    debit=Decimal('0'), kredit=bunga_paid,
                ))
            JurnalDetail.objects.bulk_create(entries)
            return header

    # Default non-PV: Dr. Kas / Cr. Piutang (tanpa_bunga or no angsuran_no)
    if piutang.coa_piutang_lancar_account_id:
        bal_lancar = max(
            Decimal('0'),
            _net_debit_balance_for_piutang(piutang.coa_piutang_lancar_account, piutang),
        )
        credit_lancar = min(jumlah, bal_lancar)
        credit_lt = jumlah - credit_lancar
        payment_lines = [
            JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                         debit=jumlah, kredit=Decimal('0')),
        ]
        if credit_lancar > 0:
            payment_lines.append(JurnalDetail(
                jurnal_header=header, akun=piutang.coa_piutang_lancar_account,
                debit=Decimal('0'), kredit=credit_lancar,
            ))
        if credit_lt > 0:
            payment_lines.append(JurnalDetail(
                jurnal_header=header, akun=piutang.coa_piutang_account,
                debit=Decimal('0'), kredit=credit_lt,
            ))
        JurnalDetail.objects.bulk_create(payment_lines)
    else:
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                         debit=jumlah, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=ar_account,
                         debit=Decimal('0'), kredit=jumlah),
        ])
    return header
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.piutang.tests.PaymentJournalPSAK71Test apps.piutang.tests.CreatePiutangPaymentTests
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): PSAK 71 payment credits piutang for full cash flow, EIR debits piutang"
```

---

## Task 7: Remove settlement catchup on full payment

**Files:**
- Modify: `apps/piutang/services.py:449-513` (inside `create_piutang_payment`)
- Modify: `apps/piutang/services.py:984-990` (inside `reverse_piutang_payment`)
- Test: `apps/piutang/tests.py`

The settlement catchup (lines 449-512) zeroed residual deferred income balances on full payment. Under PSAK 71 there is no deferred income account, so no catchup is needed. Remove the block entirely. Also remove the corresponding catchup-reversal logic in `reverse_piutang_payment`.

- [ ] **Step 1: Write test**

Add to `apps/piutang/tests.py`:

```python
class SettlementCatchupRemovedTest(TestCase):
    """Under PSAK 71, full payment should NOT create a separate catchup journal."""

    def setUp(self):
        self.f = make_fixtures()
        self.coa_rev = Akun.objects.create(
            kategori_id='pendapatan', nama='Pend Catchup', kode_akun='4.1.76',
        )
        self.coa_deferred = Akun.objects.create(
            kategori_id='kewajiban', nama='PBD Catchup', kode_akun='1.3.55',
        )
        self.coa_income = Akun.objects.create(
            kategori_id='pendapatan', nama='PBE Catchup', kode_akun='4.2.15',
        )
        from apps.piutang.services import post_piutang
        self.p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2027, 1, 1),
            jenis_jangka_waktu='long_term',
            pv_discount_rate=Decimal('12'),
            deferred_income_account=self.coa_deferred,
            interest_income_account=self.coa_income,
            details=[{
                'deskripsi': 'X', 'jumlah': Decimal('12000000'),
                'revenue_account': self.coa_rev,
            }],
        )
        post_piutang(self.p)
        self.p.refresh_from_db()

    def test_full_payment_creates_no_pelunasan_catchup_journal(self):
        from apps.jurnal.models import JurnalHeader
        create_piutang_payment(
            self.p,
            {'tanggal_terima': date(2026, 6, 1),
             'jumlah_diterima': self.p.jumlah_pokok,
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        catchup = JurnalHeader.objects.filter(
            uraian_transaksi__contains='Pelunasan'
        )
        self.assertEqual(catchup.count(), 0)
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.SettlementCatchupRemovedTest
```

Expected: Fails — catchup journal exists.

- [ ] **Step 3: Implement**

In `create_piutang_payment`, delete the entire block from line 449 to 513:

```python
        # DELETE THIS ENTIRE BLOCK (was: settlement catch-up for deferred income):
        if (piutang.status == 'paid'
                and piutang.is_pv_adjusted
                ...
                ):
            ...  # remove all lines through the closing of this block
```

In `reverse_piutang_payment`, delete lines 984-990:

```python
            # DELETE:
            if was_paid:
                catch_up = JurnalHeader.objects.filter(
                    uraian_transaksi__startswith=f'Amortisasi PV Piutang {nom} — Pelunasan',
                ).first()
                if catch_up:
                    catch_up.details.all().delete()
                    catch_up.delete()
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.piutang.tests.SettlementCatchupRemovedTest apps.piutang.tests.ReversePiutangPaymentTests apps.piutang.tests.AutoReversePenyisihanOnPaymentTest
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): remove SAK ETAP deferred income settlement catchup (PSAK 71 not needed)"
```

---

## Task 8: Update reklasifikasi to transfer carrying amount only

**Files:**
- Modify: `apps/piutang/services.py:727-892` (`_compute_rkl_detail`, `create_reklasifikasi_bagian_lancar`)
- Modify: `apps/piutang/views.py:1053-1086` (`piutang_reklasifikasi_bagian_lancar`, `piutang_set_akun_lancar`)
- Test: `apps/piutang/tests.py`

**SAK ETAP (old):** Two pairs of journal entries — (1) Cr. Piutang LT / Dr. Piutang BL for `nominal_current`; (2) Dr. Deferred LT / Cr. Deferred BL for `deferred_current`.

**PSAK 71 (new):** One pair — `Dr. Piutang BL / Cr. Piutang LT` for `carrying_current` where `carrying_current = nominal_current − deferred_current`. This is the PV of current-year cash flows.

`_compute_rkl_detail` now returns a single `Decimal` (carrying amount), not a tuple. Update its sole caller `create_reklasifikasi_bagian_lancar` accordingly. Keep `dari_akun_deferred` / `ke_akun_deferred` parameters on `create_reklasifikasi_bagian_lancar` for signature compatibility but ignore them.

- [ ] **Step 1: Write failing test**

Add to `apps/piutang/tests.py`:

```python
class ReklasifikasiPSAK71Test(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.coa_lt = Akun.objects.create(
            kategori_id='aset', nama='Piutang JK Panjang PSAK71', kode_akun='1.3.3',
        )
        self.coa_bl = Akun.objects.create(
            kategori_id='aset', nama='Piutang Bagian Lancar PSAK71', kode_akun='1.1.9',
        )
        self.coa_rev = Akun.objects.create(
            kategori_id='pendapatan', nama='Pend Rkl', kode_akun='4.1.77',
        )
        self.coa_deferred = Akun.objects.create(
            kategori_id='kewajiban', nama='PBD Rkl', kode_akun='1.3.56',
        )
        self.coa_deferred_bl = Akun.objects.create(
            kategori_id='kewajiban', nama='PBD BL Rkl', kode_akun='1.1.11',
        )
        self.coa_income = Akun.objects.create(
            kategori_id='pendapatan', nama='PBE Rkl', kode_akun='4.2.16',
        )
        from apps.piutang.services import post_piutang
        self.p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.coa_lt,
            jatuh_tempo=date(2028, 1, 1),
            jenis_jangka_waktu='long_term',
            pv_discount_rate=Decimal('12'),
            deferred_income_account=self.coa_deferred,
            interest_income_account=self.coa_income,
            coa_piutang_lancar_account=self.coa_bl,
            deferred_income_lancar_account=self.coa_deferred_bl,
            details=[{
                'deskripsi': 'X', 'jumlah': Decimal('24000000'),
                'revenue_account': self.coa_rev,
            }],
        )
        post_piutang(self.p)
        self.p.refresh_from_db()

    def test_reklasifikasi_journal_has_exactly_two_lines(self):
        from apps.piutang.services import create_reklasifikasi_bagian_lancar
        rkl = create_reklasifikasi_bagian_lancar(
            piutang=self.p,
            dari_akun=self.coa_lt,
            ke_akun=self.coa_bl,
            tanggal=date(2026, 12, 31),
            dari_akun_deferred=self.coa_deferred,
            ke_akun_deferred=self.coa_deferred_bl,
        )
        # PSAK 71: only two journal lines (Dr. current / Cr. LT), no deferred lines
        details = list(rkl.jurnal.details.all())
        self.assertEqual(len(details), 2)

    def test_reklasifikasi_debits_current_account_not_deferred(self):
        from apps.piutang.services import create_reklasifikasi_bagian_lancar
        from apps.jurnal.models import JurnalDetail
        rkl = create_reklasifikasi_bagian_lancar(
            piutang=self.p,
            dari_akun=self.coa_lt,
            ke_akun=self.coa_bl,
            tanggal=date(2026, 12, 31),
            dari_akun_deferred=self.coa_deferred,
            ke_akun_deferred=self.coa_deferred_bl,
        )
        deferred_hits = JurnalDetail.objects.filter(
            jurnal_header=rkl.jurnal,
            akun__in=[self.coa_deferred, self.coa_deferred_bl],
        )
        self.assertEqual(deferred_hits.count(), 0)
        dr_line = rkl.jurnal.details.get(debit__gt=0)
        self.assertEqual(dr_line.akun, self.coa_bl)

    def test_reklasifikasi_amount_is_carrying_not_nominal(self):
        from apps.piutang.services import create_reklasifikasi_bagian_lancar
        rkl = create_reklasifikasi_bagian_lancar(
            piutang=self.p,
            dari_akun=self.coa_lt,
            ke_akun=self.coa_bl,
            tanggal=date(2026, 12, 31),
        )
        # Carrying amount < nominal because PV discount applies
        self.assertLess(rkl.jumlah, Decimal('24000000'))
        self.assertGreater(rkl.jumlah, Decimal('0'))
```

- [ ] **Step 2: Run test to confirm it fails**

```
python manage.py test apps.piutang.tests.ReklasifikasiPSAK71Test
```

Expected: Fails — 4 journal lines (nominal + deferred pairs), not 2.

- [ ] **Step 3: Implement `_compute_rkl_detail`**

Replace `_compute_rkl_detail` in `apps/piutang/services.py` (lines 727-808):

```python
def _compute_rkl_detail(piutang: PiutangHeader, as_of_date) -> Decimal:
    """
    PSAK 71: carrying amount of current-year installments.

    carrying_current = Σ(CF_i − gross_EIR_i) for unpaid installments in (as_of_date, as_of_date+12mo]
                     = nominal_current − net_amortization_current
                     = sum of (principal_i + coupon_i − effective_interest_i)

    Returns Decimal('0') if no current installments exist.
    """
    try:
        cutoff = as_of_date.replace(year=as_of_date.year + 1)
    except ValueError:
        cutoff = as_of_date.replace(year=as_of_date.year + 1, day=28)

    schedule = compute_angsuran_schedule(piutang)
    if schedule:
        all_unpaid = [r for r in schedule if r['status'] != 'lunas']
        current_rows = [
            r for r in all_unpaid
            if as_of_date < r['tanggal'] <= cutoff
        ]
        nominal_current = sum(
            max(
                Decimal('0'),
                row['pokok'] - max(Decimal('0'), row.get('paid', Decimal('0')) - row['bunga']),
            )
            for row in current_rows
        )
    else:
        nominal_current = (
            piutang.sisa_piutang
            if piutang.jatuh_tempo and as_of_date < piutang.jatuh_tempo <= cutoff
            else Decimal('0')
        )

    if nominal_current <= 0:
        return Decimal('0')

    if not piutang.is_pv_adjusted or not piutang.nilai_wajar_awal:
        return nominal_current

    if schedule:
        amort = compute_amortization_schedule_pv(piutang)
        if amort:
            # net_amortization per due-date (EIR_gross − coupon); can be negative for premium bonds
            amort_by_date = {r['tanggal']: r['bunga_efektif'] for r in amort}
            net_amort_current = sum(
                amort_by_date.get(row['tanggal'], Decimal('0'))
                for row in current_rows
            ).quantize(Decimal('0.0001'))
        else:
            net_amort_current = Decimal('0')
    else:
        # Bullet loan fallback
        i_daily = (1 + float(piutang.pv_discount_rate) / 100) ** (1 / 365) - 1
        pv_current = Decimal('0')
        if piutang.jatuh_tempo:
            days = (piutang.jatuh_tempo - as_of_date).days
            if days > 0:
                pv_current = piutang.sisa_piutang / Decimal(str((1 + i_daily) ** days))
        net_amort_current = (nominal_current - pv_current).quantize(Decimal('0.0001'))

    carrying_current = (nominal_current - net_amort_current).quantize(Decimal('0.0001'))
    return max(Decimal('0'), carrying_current)
```

- [ ] **Step 4: Implement `create_reklasifikasi_bagian_lancar`**

Replace `create_reklasifikasi_bagian_lancar` in `apps/piutang/services.py` (lines 811-892):

```python
def create_reklasifikasi_bagian_lancar(
    piutang: PiutangHeader,
    dari_akun,
    ke_akun,
    tanggal,
    user=None,
    dari_akun_deferred=None,
    ke_akun_deferred=None,
) -> PiutangReklasifikasi:
    """
    PSAK 71: reklasifikasi carrying amount (not nominal + deferred separately).
    dari_akun_deferred / ke_akun_deferred are accepted for signature compatibility but ignored.
    """
    periode_bulan = tanggal.month
    periode_tahun = tanggal.year
    if PiutangReklasifikasi.objects.filter(
        piutang_header=piutang,
        periode_bulan=periode_bulan,
        periode_tahun=periode_tahun,
    ).exists():
        raise ValueError(
            f'Reklasifikasi bagian lancar untuk periode {periode_tahun}-{periode_bulan:02d} sudah ada.'
        )

    carrying_current = _compute_rkl_detail(piutang, tanggal)
    if carrying_current <= 0:
        raise ValueError('Tidak ada bagian lancar yang dapat direklasifikasi.')

    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-RKL')
        jurnal = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Reklasifikasi Bagian Lancar {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=jurnal, akun=dari_akun,
                         debit=Decimal('0'), kredit=carrying_current),
            JurnalDetail(jurnal_header=jurnal, akun=ke_akun,
                         debit=carrying_current, kredit=Decimal('0')),
        ])

        rkl = PiutangReklasifikasi.objects.create(
            piutang_header=piutang,
            tanggal=tanggal,
            dari_akun=dari_akun,
            ke_akun=ke_akun,
            jumlah=carrying_current,
            jumlah_deferred=None,
            dari_akun_deferred=None,
            ke_akun_deferred=None,
            keterangan=f'Bagian lancar {periode_tahun}-{periode_bulan:02d}',
            jurnal=jurnal,
            periode_bulan=periode_bulan,
            periode_tahun=periode_tahun,
            created_by=user,
        )
        _log(piutang, 'REKLASIFIKASI', user=user,
             after={'jumlah': str(carrying_current)})
    return rkl
```

- [ ] **Step 5: Update views to stop passing deferred accounts**

In `apps/piutang/views.py`, `piutang_reklasifikasi_bagian_lancar` (around line 1063), remove the deferred account lines:

```python
# DELETE THESE LINES:
dari_akun_deferred = piutang.deferred_income_account
ke_akun_deferred = piutang.deferred_income_lancar_account

# And remove them from the call:
create_reklasifikasi_bagian_lancar(
    piutang=piutang,
    dari_akun=dari_akun,
    ke_akun=ke_akun,
    tanggal=tanggal,
    user=request.user,
    # dari_akun_deferred and ke_akun_deferred are no longer passed
)
```

In `piutang_set_akun_lancar` (around line 1040-1045), remove `deferred_income_lancar_account` save:

```python
# Change to only save coa_piutang_lancar_account:
piutang.coa_piutang_lancar_account = Akun.objects.get(pk=lancar_id) if lancar_id else None
piutang.save(update_fields=['coa_piutang_lancar_account'])
```

(The `deferred_income_lancar_account` field stays in the DB but is no longer updated via this view under PSAK 71.)

- [ ] **Step 6: Run tests**

```
python manage.py test apps.piutang.tests.ReklasifikasiPSAK71Test apps.piutang.tests.CreateReklasifikasiBagianLancarTest
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add apps/piutang/services.py apps/piutang/views.py apps/piutang/tests.py
git commit -m "feat(piutang): PSAK 71 reklasifikasi transfers carrying amount only (no deferred)"
```

---

## Task 9: Remove unused helper functions and clean up

**Files:**
- Modify: `apps/piutang/services.py`

After Tasks 3–6, `_contractual_interest_in_period` and `_pv_net_amortized` are no longer called by any active code path. Remove them to prevent confusion.

- [ ] **Step 1: Verify nothing imports these functions externally**

```bash
grep -rn "_contractual_interest_in_period\|_pv_net_amortized\|_pv_pokok_paid" apps/ --include="*.py"
```

Expected output: Only definitions in `services.py` (no external callers).

- [ ] **Step 2: Delete `_contractual_interest_in_period` (lines 1735-1751)**

Remove the entire function block. It was used to compute `net_amortization = EIR − coupon` for old SAK ETAP journals.

- [ ] **Step 3: Delete `_pv_net_amortized` (lines 1707-1732) and `_pv_pokok_paid` (lines 1754-1781)**

These were used only by the old `_pv_carrying_value` formula. They were replaced by the account-balance approach in Task 3.

- [ ] **Step 4: Run full test suite**

```
python manage.py test apps.piutang
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py
git commit -m "refactor(piutang): remove SAK ETAP helper functions unused after PSAK 71 migration"
```

---

## Task 10: Full suite regression check

- [ ] **Step 1: Run all piutang tests**

```
python manage.py test apps.piutang -v 2
```

Expected: All pass, no unexpected failures.

- [ ] **Step 2: Smoke-check the existing reklasifikasi test still passes**

```
python manage.py test apps.piutang.tests.CreateReklasifikasiBagianLancarTest
```

- [ ] **Step 3: Verify journal balance integrity for a full lifecycle**

Run this in Django shell to verify a PV piutang lifecycle produces balanced journals:

```python
from django.test.utils import setup_test_environment
setup_test_environment()

# In tests: post → amortize period 1 → pay installment 1 → reklasifikasi → pay remaining
# Verify: total debits == total credits across all journals for the piutang
```

- [ ] **Step 4: Final commit tag**

```bash
git tag psak71-amortised-cost-complete
```

---

## Self-Review Checklist

- [x] **Initial recognition** covered: Task 2 — Dr. Piutang (PV) / Cr. Revenue (PV), no deferred
- [x] **EIR amortization** covered: Task 4 — Dr. Piutang / Cr. Income (gross EIR)
- [x] **EIR accrual** covered: Task 5 — Dr. Piutang / Cr. Income (gross EIR)
- [x] **Payment** covered: Task 6 — Dr. Cash / Cr. Piutang (full cash flow)
- [x] **Carrying value** covered: Task 3 — reads piutang account balance
- [x] **Reklasifikasi** covered: Task 8 — single carrying amount transfer
- [x] **Settlement catchup** removed: Task 7
- [x] **Cleanup** covered: Task 9
- [x] No SAK ETAP deferred income accounts are posted to in any new code path
- [x] `deferred_income_account` and `deferred_income_lancar_account` model fields are kept (backward compat) but not used in new journal entries
- [x] Non-PV-adjusted piutang paths are unchanged
- [x] `bunga_efektif_gross` added to schedule (Task 1) before it is consumed (Task 4)
