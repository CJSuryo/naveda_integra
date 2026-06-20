# Multi-Tax Per KP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a single KewajibabPelaksanaan (KP) to carry multiple tax lines simultaneously (e.g., PPN Keluaran + PPh 23 on one sale), with all tax logic centralized in `apps.pajak`.

**Architecture:** Introduce a new `KPTaxLine` model (FK → KP CASCADE, `related_name='tax_lines'`) to replace the four single-tax fields currently on `KewajibabPelaksanaan`. `apps.pajak.services.sync_pajak` gains an `override_amount` parameter so callers can pass a per-line manual amount without relying on `source_obj.tax`. The `pendapatan` form renders a dynamic multi-row tax section per KP via JS, posting flat field names (`item_0_tax_0_tax_type`, etc.) that the view parses manually.

**Tech Stack:** Django 6.x / Python 3.12, PostgreSQL, vanilla JS (no framework)

**Test runner:** `python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test`

---

## File Map

| File | Change |
|---|---|
| `apps/pendapatan/models.py` | Add `KPTaxLine` model; remove `tax`, `tax_type`, `tax_account`, `tax_payment`, `tax_payment_account` from `KewajibabPelaksanaan` |
| `apps/pendapatan/migrations/0008_kp_tax_lines.py` | New: CreateModel KPTaxLine + RunPython data-migrate + RemoveField ×5 |
| `apps/pajak/services.py` | Add `override_amount=None` parameter to `sync_pajak` |
| `apps/pendapatan/services.py` | Replace single-tax helpers with multi-tax variants; update all callers |
| `apps/pendapatan/forms.py` | Remove 4 tax fields from `KewajibabPelaksanaanForm`; add `KPTaxLineForm` |
| `apps/pendapatan/views.py` | Parse tax lines per item in create/edit; pass `tax_lines_initial_json` for edit GET |
| `templates/pendapatan/form.html` | Replace single-tax section with multi-tax rows + JS |
| `apps/pajak/tests/test_pendapatan_integration.py` | Switch items dict to `tax_lines` key; add dual-tax test |

---

## Task 1: KPTaxLine model + migration

**Files:**
- Modify: `apps/pendapatan/models.py`
- Create: `apps/pendapatan/migrations/0008_kp_tax_lines.py`

- [ ] **Step 1: Add KPTaxLine model to models.py**

  Open `apps/pendapatan/models.py`. After the `KewajibabPelaksanaan` class (around line 241), insert the new model, and remove the five single-tax fields from `KewajibabPelaksanaan`.

  **Remove these fields from `KewajibabPelaksanaan`** (lines 181–191):
  ```python
  # DELETE these 5 fields:
  tax = models.DecimalField(...)
  tax_type = models.CharField(...)
  tax_account = models.ForeignKey(...)
  tax_payment = models.CharField(...)
  tax_payment_account = models.ForeignKey(...)
  ```

  **Add `KPTaxLine` class after `KewajibabPelaksanaan.__str__`:**
  ```python
  class KPTaxLine(models.Model):
      kp = models.ForeignKey(
          KewajibabPelaksanaan, on_delete=models.CASCADE, related_name='tax_lines',
          verbose_name='Kewajiban Pelaksanaan',
      )
      tax_type = models.CharField(max_length=30, choices=TAX_TYPE_CHOICES, verbose_name='Tipe Pajak')
      tax = models.DecimalField(
          max_digits=19, decimal_places=4, null=True, blank=True,
          verbose_name='Pajak (Override Manual)',
          help_text='Jika diisi, nilai ini menggantikan perhitungan tarif otomatis.',
      )
      tax_account = models.ForeignKey(
          'master_data.Akun', on_delete=models.PROTECT,
          related_name='kp_tax_lines_pajak', verbose_name='Akun Pajak',
      )
      tax_payment_account = models.ForeignKey(
          'master_data.Akun', on_delete=models.PROTECT,
          related_name='kp_tax_lines_lawan', verbose_name='Akun Lawan Pajak',
      )

      class Meta:
          verbose_name = 'KP Tax Line'
          verbose_name_plural = 'KP Tax Lines'
          ordering = ['id']

      def __str__(self) -> str:
          return f'KP-{self.kp_id} — {self.tax_type}'
  ```

  Also remove `TAX_PAYMENT_CHOICES` list if nothing else uses it (check with grep first — it's only used by the removed `tax_payment` field).

- [ ] **Step 2: Write migration 0008**

  Create `apps/pendapatan/migrations/0008_kp_tax_lines.py`:

  ```python
  from django.db import migrations, models
  import django.db.models.deletion


  def migrate_tax_data(apps, schema_editor):
      KPTaxLine = apps.get_model('pendapatan', 'KPTaxLine')
      KewajibabPelaksanaan = apps.get_model('pendapatan', 'KewajibabPelaksanaan')
      for kp in KewajibabPelaksanaan.objects.exclude(tax_type='').filter(
          tax_account__isnull=False,
          tax_payment_account__isnull=False,
      ):
          KPTaxLine.objects.create(
              kp=kp,
              tax_type=kp.tax_type,
              tax=kp.tax,
              tax_account_id=kp.tax_account_id,
              tax_payment_account_id=kp.tax_payment_account_id,
          )


  def reverse_migrate_tax_data(apps, schema_editor):
      KPTaxLine = apps.get_model('pendapatan', 'KPTaxLine')
      KewajibabPelaksanaan = apps.get_model('pendapatan', 'KewajibabPelaksanaan')
      for tl in KPTaxLine.objects.select_related('kp').all():
          kp = tl.kp
          kp.tax_type = tl.tax_type
          kp.tax = tl.tax
          kp.tax_account_id = tl.tax_account_id
          kp.tax_payment_account_id = tl.tax_payment_account_id
          kp.save(update_fields=['tax_type', 'tax', 'tax_account_id', 'tax_payment_account_id'])


  class Migration(migrations.Migration):
      dependencies = [
          ('pendapatan', '0007_psak72_cleanup'),
          ('master_data', '__first__'),
      ]

      operations = [
          migrations.CreateModel(
              name='KPTaxLine',
              fields=[
                  ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                  ('tax_type', models.CharField(choices=[('ppn_keluaran', 'PPN Keluaran'), ('pph_23', 'PPh 23'), ('pph_21', 'PPh 21'), ('pph_4_2', 'PPh 4(2)')], max_length=30, verbose_name='Tipe Pajak')),
                  ('tax', models.DecimalField(blank=True, decimal_places=4, max_digits=19, null=True, verbose_name='Pajak (Override Manual)')),
                  ('kp', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tax_lines', to='pendapatan.kewajibabpelaksanaan', verbose_name='Kewajiban Pelaksanaan')),
                  ('tax_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='kp_tax_lines_pajak', to='master_data.akun', verbose_name='Akun Pajak')),
                  ('tax_payment_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='kp_tax_lines_lawan', to='master_data.akun', verbose_name='Akun Lawan Pajak')),
              ],
              options={'verbose_name': 'KP Tax Line', 'verbose_name_plural': 'KP Tax Lines', 'ordering': ['id']},
          ),
          migrations.RunPython(migrate_tax_data, reverse_code=reverse_migrate_tax_data),
          migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax'),
          migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_type'),
          migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_account'),
          migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_payment'),
          migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_payment_account'),
      ]
  ```

  Note: the `master_data` dependency label may already be implicit; if Django complains, remove it and rely on auto-detection.

- [ ] **Step 3: Run migrations and verify**

  ```powershell
  python manage.py migrate --settings=naveda_integra.settings.test
  ```

  Expected: `0008_kp_tax_lines` applies cleanly.

- [ ] **Step 4: Run existing tests to confirm nothing regressed**

  ```powershell
  python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
  ```

  Expected: All non-piutang tests still pass (the integration tests will fail because `items` still reference `tax_type` etc. — that's fixed in Task 7).

- [ ] **Step 5: Commit**

  ```bash
  git add apps/pendapatan/models.py apps/pendapatan/migrations/0008_kp_tax_lines.py
  git commit -m "feat(pendapatan): add KPTaxLine model, migrate single-tax fields to tax_lines"
  ```

---

## Task 2: Update apps/pajak/services.py — add `override_amount` to `sync_pajak`

**Files:**
- Modify: `apps/pajak/services.py:77-130`

- [ ] **Step 1: Write a failing test for override_amount**

  In `apps/pajak/tests/test_services.py`, add to an existing TestCase or create a new test:

  ```python
  def test_sync_pajak_override_amount_takes_priority_over_source_tax(self):
      """override_amount param bypasses compute_pajak and source_obj.tax."""
      from apps.pajak.services import sync_pajak, confirm_pajak
      from decimal import Decimal

      # source_obj.tax = 99 but override_amount = 50000 → should use 50000
      class FakeKP:
          pk = 9999
          tax = Decimal('99')
          entitas_bisnis = None

      result = sync_pajak(
          source_type='test',
          source_obj=FakeKP(),
          dpp=Decimal('500000'),
          tanggal=date(2026, 6, 1),
          jenis_pajak='ppn_umum',
          akun_pajak=self.coa_ppn,
          akun_lawan=self.coa_kas,
          sifat_pajak='potong_pungut',
          override_amount=Decimal('50000'),
      )
      self.assertEqual(result.jumlah_pajak, Decimal('50000'))
      self.assertTrue(result.is_overridden)
  ```

  Run test — expect FAIL (no `override_amount` param yet):
  ```powershell
  python manage.py test apps.pajak.tests.test_services --settings=naveda_integra.settings.test
  ```

- [ ] **Step 2: Add `override_amount` to `sync_pajak`**

  In `apps/pajak/services.py`, modify the function signature and logic:

  ```python
  def sync_pajak(
      source_type: str,
      source_obj,
      dpp: Decimal,
      tanggal: date,
      jenis_pajak: str,
      akun_pajak,
      akun_lawan,
      sifat_pajak: str,
      override_amount: Decimal | None = None,
  ) -> PajakTransaksi:
      """
      Create a draft PajakTransaksi for source_obj.

      Priority for jumlah_pajak:
        1. override_amount (if provided and > 0) → is_overridden=True
        2. source_obj.tax (if attribute exists and > 0) → is_overridden=True
        3. compute_pajak from TarifPajak → is_overridden=False
      Raises MasaPajakTerkunciError if the target period is locked.
      """
      masa_date = tanggal.replace(day=1)
      masa, _ = MasaPajak.objects.get_or_create(
          tahun=masa_date.year, bulan=masa_date.month,
          defaults={'status': 'open'},
      )
      if masa.status == 'locked':
          raise MasaPajakTerkunciError(
              f'Masa pajak {masa_date:%Y-%m} sudah terkunci. '
              'Buka kunci terlebih dahulu sebelum memposting transaksi baru.'
          )

      effective_override = (
          override_amount if (override_amount is not None and override_amount > 0)
          else getattr(source_obj, 'tax', None)
      )
      if effective_override and effective_override > 0:
          jumlah_pajak = effective_override
          tarif_persen = Decimal('0')
          is_overridden = True
      else:
          hasil = compute_pajak(jenis_pajak, dpp, tanggal)
          jumlah_pajak = hasil['jumlah_pajak']
          tarif_persen = hasil['tarif_persen']
          is_overridden = False

      return PajakTransaksi.objects.create(
          source_type=source_type,
          source_id=source_obj.pk,
          masa_pajak=masa_date,
          jenis_pajak=jenis_pajak,
          dpp=dpp,
          tarif_persen=tarif_persen,
          jumlah_pajak=jumlah_pajak,
          sifat_pajak=sifat_pajak,
          status='draft',
          is_overridden=is_overridden,
          akun_pajak=akun_pajak,
          akun_lawan=akun_lawan,
          entitas_bisnis=getattr(source_obj, 'entitas_bisnis', None),
      )
  ```

- [ ] **Step 3: Run test — expect PASS**

  ```powershell
  python manage.py test apps.pajak.tests.test_services --settings=naveda_integra.settings.test
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add apps/pajak/services.py apps/pajak/tests/test_services.py
  git commit -m "feat(pajak): add override_amount param to sync_pajak"
  ```

---

## Task 3: Update apps/pendapatan/services.py — multi-tax helpers

**Files:**
- Modify: `apps/pendapatan/services.py`

The changes are:
1. Replace `_maybe_sync_confirm_pajak` → `_sync_confirm_tax_line(kp, header, tax_line, amount, user=None)`
2. Replace `_prorate_tax` → `_prorate_tax_lines(kp, amount, nilai_total) -> list[dict]`
3. Update `_create_recognition_journal`: change `tax_amount=Decimal('0')` → `tax_lines_data: list | None = None`
4. Update `create_pendapatan_header`: use individual creates + KPTaxLine creation
5. Update `confirm_pendapatan`: 3 call sites + updated prefetch
6. Update `recognize_entry` + `recognize_percentage_completion`: use `_prorate_tax_lines`
7. Update `_create_pendapatan_journals` (legacy at bottom): iterate `kp.tax_lines.all()`
8. Remove import of `KPTaxLine` isn't needed (it lives in same models module)

- [ ] **Step 1: Update imports in services.py**

  The models import at the top currently has:
  ```python
  from .models import (
      AsetKontrak, EntriPengakuan, JadwalPengakuan,
      KewajibabPelaksanaan, PendapatanEntitasBisnis, PendapatanEventLog, PendapatanHeader, PendapatanItem,
  )
  ```
  Add `KPTaxLine` to this import:
  ```python
  from .models import (
      AsetKontrak, EntriPengakuan, JadwalPengakuan, KPTaxLine,
      KewajibabPelaksanaan, PendapatanEntitasBisnis, PendapatanEventLog, PendapatanHeader, PendapatanItem,
  )
  ```

- [ ] **Step 2: Replace `_maybe_sync_confirm_pajak` with `_sync_confirm_tax_line`**

  Find and replace the entire `_maybe_sync_confirm_pajak` function (lines ~241–270) with:

  ```python
  def _sync_confirm_tax_line(kp, header, tax_line: 'KPTaxLine', amount, user=None):
      """
      Create and immediately confirm a PajakTransaksi for one KPTaxLine.
      Called inside the transaction.atomic() of confirm_pendapatan.
      """
      jenis_pajak = TAX_TYPE_MAP.get(tax_line.tax_type)
      if not jenis_pajak:
          return
      akun_pajak = tax_line.tax_account
      akun_lawan = tax_line.tax_payment_account
      sifat_pajak = SIFAT_PAJAK_MAP.get(tax_line.tax_type, 'potong_pungut')

      pajak_trx = sync_pajak(
          source_type='pendapatan_kp',
          source_obj=kp,
          dpp=amount,
          tanggal=header.tanggal,
          jenis_pajak=jenis_pajak,
          akun_pajak=akun_pajak,
          akun_lawan=akun_lawan,
          sifat_pajak=sifat_pajak,
          override_amount=tax_line.tax,
      )
      confirm_pajak_trx(pajak_trx)
  ```

- [ ] **Step 3: Update `confirm_pendapatan` — prefetch + 3 call sites**

  In `confirm_pendapatan`, update the `prefetch_related` at the `for eb_group in ...` loop:

  ```python
  for eb_group in header.entitas_groups.prefetch_related(
      'items__revenue_account', 'items__payment_account',
      'items__tax_lines__tax_account', 'items__tax_lines__tax_payment_account',
      'items__ot_liabilitas_kontrak_acct', 'items__ot_aset_kontrak_acct',
  ).all():
  ```

  Replace the three `_maybe_sync_confirm_pajak(kp, header, kp.tax_type, harga_j, user=user)` calls with:

  ```python
  for tax_line in kp.tax_lines.all():
      _sync_confirm_tax_line(kp, header, tax_line, harga_j, user=user)
  ```

  All three occurrences (Case 1 point_in_time, Case 3 advance_payment_cash, Case 5 performance_first) get this same replacement.

- [ ] **Step 4: Replace `_prorate_tax` with `_prorate_tax_lines`**

  Remove `_prorate_tax` (lines ~616–620) and add:

  ```python
  def _prorate_tax_lines(kp, amount: Decimal, nilai_total: Decimal) -> list[dict]:
      """
      Return [{akun: Akun, amount: Decimal}, ...] for each KPTaxLine, prorated
      by amount/nilai_total. Lines with no override use kp.tax_lines as-is for
      account lookup only; the prorated amount is the caller's responsibility.
      """
      if nilai_total <= 0:
          return []
      result = []
      for tl in kp.tax_lines.select_related('tax_account').all():
          if tl.tax and tl.tax > 0:
              prorated = (tl.tax * amount / nilai_total).quantize(Decimal('0.0001'))
              result.append({'akun': tl.tax_account, 'amount': prorated})
      return result
  ```

  Note: `_prorate_tax_lines` only prorates tax lines that have a manual override amount (`tl.tax`). For lines using tarif-based amounts, the tax was already posted at `confirm_pendapatan` via `sync_pajak`; periodic_billing only needs to prorate the manual override portion here.

- [ ] **Step 5: Update `_create_recognition_journal`**

  Replace the current signature and body:

  ```python
  def _create_recognition_journal(
      header, eb_group, kp, debit_acct, credit_acct, amount,
      journal_date=None, user=None, tax_lines_data: list | None = None,
  ):
      """
      Create recognition journal for EntriPengakuan.
      tax_lines_data: list of {'akun': Akun, 'amount': Decimal}.
      When present:
        Dr debit_acct  (amount + sum(tl.amount))
        Cr credit_acct (amount)
        Cr tl.akun     (tl.amount)  for each tl
      """
      if debit_acct is None:
          raise ValueError(
              f'KP "{kp.deskripsi_item}" tidak memiliki akun debit untuk pengakuan pendapatan.'
          )
      if credit_acct is None:
          raise ValueError(
              f'KP "{kp.deskripsi_item}" tidak memiliki akun kredit untuk pengakuan pendapatan.'
          )
      from django.utils import timezone as tz
      tanggal = journal_date or tz.now().date()
      tax_lines_data = tax_lines_data or []
      total_tax = sum(tl['amount'] for tl in tax_lines_data)
      debit_total = amount + total_tax
      nomor = _next_journal_number('TRX-PND-RE')
      jh = JurnalHeader.objects.create(
          tanggal=tanggal,
          nomor_transaksi=nomor,
          uraian_transaksi=(
              f'Pengakuan Pendapatan {header.transaction_id} — {eb_group.entitas_bisnis.nama} — KP {kp.pk}'
          ),
          entitas_bisnis=eb_group.entitas_bisnis,
          is_penyesuaian=False,
      )
      details = [
          JurnalDetail(jurnal_header=jh, akun=debit_acct, debit=debit_total, kredit=Decimal('0')),
          JurnalDetail(jurnal_header=jh, akun=credit_acct, debit=Decimal('0'), kredit=amount),
      ]
      for tl in tax_lines_data:
          details.append(
              JurnalDetail(jurnal_header=jh, akun=tl['akun'], debit=Decimal('0'), kredit=tl['amount'])
          )
      JurnalDetail.objects.bulk_create(details)
      _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)
      return jh
  ```

- [ ] **Step 6: Update `recognize_entry` and `recognize_percentage_completion`**

  In both functions, replace:
  ```python
  # OLD:
  'jadwal__kp__tax_account',
  # ...
  prorated_tax = _prorate_tax(kp, amount, jadwal.nilai_total)
  jh = _create_recognition_journal(..., tax_amount=prorated_tax)
  ```

  With (in `recognize_entry` select_related, remove `'jadwal__kp__tax_account'` and add prefetch):
  ```python
  entri = EntriPengakuan.objects.select_related(
      'jadwal__kp__pendapatan_eb__pendapatan_header',
      'jadwal__kp__pendapatan_eb__payment_account',
      'jadwal__kp__revenue_account',
      'jadwal__kp__payment_account',
      'jadwal__liabilitas_kontrak_acct',
  ).prefetch_related(
      'jadwal__kp__tax_lines__tax_account',
  ).get(pk=entry_id)
  ```

  And in the `periodic_billing` branch of both `recognize_entry` and `recognize_percentage_completion`:
  ```python
  elif tipe_aliran == 'periodic_billing':
      pay_acct = kp.payment_account or eb_group.payment_account
      tax_lines_data = _prorate_tax_lines(kp, amount, jadwal.nilai_total)
      jh = _create_recognition_journal(
          header=header, eb_group=eb_group, kp=kp,
          debit_acct=pay_acct, credit_acct=kp.revenue_account,
          amount=amount, journal_date=journal_date, user=user,
          tax_lines_data=tax_lines_data,
      )
  ```

  Similarly for `recognize_percentage_completion` — same `periodic_billing` branch update.

  Also update `recognize_percentage_completion`'s `select_related`:
  ```python
  jadwal = JadwalPengakuan.objects.select_related(
      'kp__pendapatan_eb__pendapatan_header',
      'kp__pendapatan_eb__entitas_bisnis',
      'kp__pendapatan_eb__payment_account',
      'kp__revenue_account',
      'kp__payment_account',
      'liabilitas_kontrak_acct',
  ).prefetch_related(
      'kp__tax_lines__tax_account',
  ).get(pk=jadwal_id)
  ```

- [ ] **Step 7: Update `create_pendapatan_header` — individual creates + KPTaxLine**

  Replace the `PendapatanItem.objects.bulk_create([...])` block with individual creates that also write KPTaxLine:

  ```python
  for item in items:
      kp = PendapatanItem.objects.create(
          pendapatan_eb=eb_group,
          deskripsi_item=item['deskripsi_item'],
          kategori=item['kategori'],
          sub_transaction_type=item['sub_transaction_type'],
          nilai_kontrak=item.get('nilai_kontrak') or item.get('jumlah_bruto'),
          revenue_account=item['revenue_account'],
          payment_account=item.get('payment_account'),
          recognition_type=item.get('recognition_type', 'point_in_time'),
          ot_tipe_aliran=item.get('ot_tipe_aliran', ''),
          ot_progress_method=item.get('ot_progress_method', ''),
          ot_tanggal_mulai=item.get('ot_tanggal_mulai'),
          ot_tanggal_selesai=item.get('ot_tanggal_selesai'),
          ot_liabilitas_kontrak_acct=item.get('ot_liabilitas_kontrak_acct'),
          ot_aset_kontrak_acct=item.get('ot_aset_kontrak_acct'),
          ot_biaya_estimasi_total=item.get('ot_biaya_estimasi_total'),
      )
      for tl in item.get('tax_lines', []):
          KPTaxLine.objects.create(
              kp=kp,
              tax_type=tl['tax_type'],
              tax=tl.get('tax'),
              tax_account=tl['tax_account'],
              tax_payment_account=tl['tax_payment_account'],
          )
  ```

- [ ] **Step 8: Update `_create_pendapatan_journals` (legacy helper at bottom)**

  This function (line ~867) still references `item.tax` and `item.tax_account`. Update the tax lines section:

  ```python
  # OLD:
  if item.tax and item.tax > 0 and item.tax_account:
      entries.append(JurnalDetail(..., akun=item.tax_account, kredit=item.tax))

  # NEW:
  for tl in item.tax_lines.select_related('tax_account').all():
      if tl.tax and tl.tax > 0:
          entries.append(JurnalDetail(
              jurnal_header=jh, akun=tl.tax_account,
              debit=Decimal('0'), kredit=tl.tax,
          ))
  ```

- [ ] **Step 9: Run tests**

  ```powershell
  python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
  ```

  The integration tests in `test_pendapatan_integration.py` will now fail because items still use old keys (`tax_type`, `tax`, etc. at top level). That's fixed in Task 7. All other tests should pass.

- [ ] **Step 10: Commit**

  ```bash
  git add apps/pendapatan/services.py
  git commit -m "refactor(pendapatan): replace single-tax helpers with multi-tax KPTaxLine iteration"
  ```

---

## Task 4: Update forms.py — KPTaxLineForm + remove old tax fields

**Files:**
- Modify: `apps/pendapatan/forms.py`

- [ ] **Step 1: Remove tax fields from `KewajibabPelaksanaanForm`**

  In `forms.py`:
  - Delete `tax`, `tax_type`, `tax_account`, `tax_payment_account` field declarations (lines 57–82)
  - Remove `TAX_TYPE_CHOICES` from the model import (it's now only needed for `KPTaxLineForm`)
  - In `KewajibabPelaksanaanForm.__init__`, remove the two lines:
    ```python
    self.fields['tax_account'].queryset = qs_all
    self.fields['tax_payment_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
    ```

- [ ] **Step 2: Add `KPTaxLineForm`**

  After the `KewajibabPelaksanaanForm` class, add:

  ```python
  class KPTaxLineForm(forms.Form):
      """Validates a single tax line submitted for a KP."""
      tax_type = forms.ChoiceField(
          choices=TAX_TYPE_CHOICES,
          widget=forms.Select(attrs={'class': 'ni-input kp-tax-type-sel'}),
          label='Tipe Pajak',
      )
      tax = forms.DecimalField(
          max_digits=19, decimal_places=4, required=False,
          widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
          label='Pajak (Nominal Override)',
      )
      tax_account = forms.ModelChoiceField(
          queryset=Akun.objects.none(),
          widget=forms.Select(attrs={'class': 'ni-input'}),
          empty_label='— Pilih Akun Pajak —',
          label='Akun Pajak',
      )
      tax_payment_account = forms.ModelChoiceField(
          queryset=Akun.objects.none(),
          widget=forms.Select(attrs={'class': 'ni-input'}),
          empty_label='— Pilih Akun Lawan —',
          label='Akun Lawan Pajak',
      )

      def __init__(self, *args, **kwargs):
          super().__init__(*args, **kwargs)
          qs_all = akun_sorted_queryset()
          self.fields['tax_account'].queryset = qs_all
          self.fields['tax_payment_account'].queryset = qs_all
  ```

  Also update the top-level `TAX_TYPE_CHOICES` import — it's still in models.py (just not on KewajibabPelaksanaan anymore), so keep the import.

- [ ] **Step 3: Run tests**

  ```powershell
  python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add apps/pendapatan/forms.py
  git commit -m "refactor(pendapatan): remove single-tax fields from KPForm, add KPTaxLineForm"
  ```

---

## Task 5: Update views.py — create + edit views

**Files:**
- Modify: `apps/pendapatan/views.py`

The view needs to:
1. Parse tax lines per item from POST (flat field names `item_i_tax_j_*`)
2. In edit GET: build `tax_lines_initial_json` from existing `kp.tax_lines.all()`
3. In edit POST: after recreating KPs, create their KPTaxLine records

- [ ] **Step 1: Add import for KPTaxLineForm + KPTaxLine model**

  At the top of views.py:
  ```python
  from .forms import PendapatanHeaderForm, PendapatanItemForm, KewajibabPelaksanaanForm, RecurringTemplateForm, KPTaxLineForm
  ```
  (Import of `KewajibabPelaksanaanForm` already there; just add `KPTaxLineForm`)

- [ ] **Step 2: Add helper function to parse tax lines from POST**

  Before `pendapatan_create`, add:

  ```python
  def _parse_tax_lines_from_post(post, item_idx: int) -> list[dict]:
      """Parse tax line POST fields for item at index item_idx."""
      from apps.master_data.models import Akun
      tax_count = int(post.get(f'item_{item_idx}_tax_count', '0') or '0')
      tax_lines = []
      for j in range(tax_count):
          tax_type = post.get(f'item_{item_idx}_tax_{j}_tax_type', '').strip()
          if not tax_type:
              continue
          tax_account_id = post.get(f'item_{item_idx}_tax_{j}_tax_account', '').strip()
          tax_payment_account_id = post.get(f'item_{item_idx}_tax_{j}_tax_payment_account', '').strip()
          if not tax_account_id or not tax_payment_account_id:
              continue
          try:
              tax_account = Akun.objects.get(pk=int(tax_account_id))
              tax_payment_account = Akun.objects.get(pk=int(tax_payment_account_id))
          except (Akun.DoesNotExist, ValueError):
              continue
          tax_raw = post.get(f'item_{item_idx}_tax_{j}_tax', '').strip()
          from decimal import Decimal, InvalidOperation
          try:
              tax = Decimal(tax_raw) if tax_raw else None
          except InvalidOperation:
              tax = None
          tax_lines.append({
              'tax_type': tax_type,
              'tax': tax,
              'tax_account': tax_account,
              'tax_payment_account': tax_payment_account,
          })
      return tax_lines
  ```

- [ ] **Step 3: Update `pendapatan_create` POST — attach tax_lines per item**

  In `pendapatan_create`, after `items = [f.cleaned_data for f in item_forms]`, add:

  ```python
  for i, item in enumerate(items):
      item['tax_lines'] = _parse_tax_lines_from_post(request.POST, i)
  ```

- [ ] **Step 4: Update `pendapatan_edit` POST — recreate KPTaxLine after bulk_create**

  In `pendapatan_edit` POST block, after `form.is_valid() and all(...)`:

  Parse tax lines first:
  ```python
  items_data = [f.cleaned_data for f in item_forms]
  for i, item in enumerate(items_data):
      item['tax_lines'] = _parse_tax_lines_from_post(request.POST, i)
  ```

  Then replace the `_KP.objects.bulk_create([...])` block with individual creates:

  ```python
  from .models import KewajibabPelaksanaan as _KP, KPTaxLine as _TL

  for item in items_data:
      kp = _KP.objects.create(
          pendapatan_eb=eb_group,
          deskripsi_item=item['deskripsi_item'],
          kategori=item['kategori'],
          sub_transaction_type=item['sub_transaction_type'],
          nilai_kontrak=item.get('nilai_kontrak') or item.get('jumlah_bruto'),
          revenue_account=item['revenue_account'],
          payment_account=item.get('payment_account'),
          recognition_type=item.get('recognition_type', 'point_in_time'),
          ot_tipe_aliran=item.get('ot_tipe_aliran', ''),
          ot_progress_method=item.get('ot_progress_method', ''),
          ot_tanggal_mulai=item.get('ot_tanggal_mulai'),
          ot_tanggal_selesai=item.get('ot_tanggal_selesai'),
          ot_liabilitas_kontrak_acct=item.get('ot_liabilitas_kontrak_acct'),
          ot_aset_kontrak_acct=item.get('ot_aset_kontrak_acct'),
          ot_biaya_estimasi_total=item.get('ot_biaya_estimasi_total'),
      )
      for tl in item.get('tax_lines', []):
          _TL.objects.create(
              kp=kp,
              tax_type=tl['tax_type'],
              tax=tl.get('tax'),
              tax_account=tl['tax_account'],
              tax_payment_account=tl['tax_payment_account'],
          )
  ```

- [ ] **Step 5: Update `pendapatan_edit` GET — tax_lines_initial_json**

  In the `else:` (GET) block of `pendapatan_edit`, after building `item_forms`, add:

  ```python
  tax_lines_initial: dict[int, list] = {}
  for i, item in enumerate(existing_items):
      tax_lines_initial[i] = [
          {
              'tax_type': tl.tax_type,
              'tax': str(tl.tax) if tl.tax else '',
              'tax_account_id': tl.tax_account_id,
              'tax_payment_account_id': tl.tax_payment_account_id,
          }
          for tl in item.tax_lines.all()
      ]
  ```

  And pass it to the template (in the `render` call for both GET and POST re-render):
  ```python
  return render(request, 'pendapatan/form.html', {
      'form': form,
      'item_forms': item_forms,
      'mode': 'edit',
      'header': header,
      'eb_options_json': json.dumps(_get_eb_dropdown_options()),
      'eb_selected': eb_selected,
      'tax_lines_initial_json': json.dumps(tax_lines_initial),
  })
  ```

  For create mode, pass an empty dict:
  ```python
  return render(request, 'pendapatan/form.html', {
      'form': form,
      'item_forms': item_forms,
      'mode': 'create',
      'eb_options_json': json.dumps(_get_eb_dropdown_options()),
      'tax_lines_initial_json': '{}',
  })
  ```

  Also update `pendapatan_edit` GET form to remove old tax initial keys:
  ```python
  item_forms = [
      KewajibabPelaksanaanForm(prefix=f'item_{i}', initial={
          'deskripsi_item': item.deskripsi_item,
          'kategori': item.kategori,
          'sub_transaction_type': item.sub_transaction_type_id,
          'nilai_kontrak': item.nilai_kontrak,
          'revenue_account': item.revenue_account_id,
          'payment_account': item.payment_account_id,
          # NOTE: no tax fields here — they come from tax_lines_initial_json
          'recognition_type': item.recognition_type,
          'ot_tipe_aliran': item.ot_tipe_aliran,
          'ot_progress_method': item.ot_progress_method,
          'ot_tanggal_mulai': item.ot_tanggal_mulai,
          'ot_tanggal_selesai': item.ot_tanggal_selesai,
          'ot_liabilitas_kontrak_acct': item.ot_liabilitas_kontrak_acct_id,
          'ot_aset_kontrak_acct': item.ot_aset_kontrak_acct_id,
          'ot_biaya_estimasi_total': item.ot_biaya_estimasi_total,
      })
      for i, item in enumerate(existing_items)
  ] or [KewajibabPelaksanaanForm(prefix='item_0')]
  ```

- [ ] **Step 6: Run tests**

  ```powershell
  python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add apps/pendapatan/views.py
  git commit -m "refactor(pendapatan): views parse multi-tax lines per item, pass initial JSON for edit"
  ```

---

## Task 6: Update form.html — multi-tax UI per KP row

**Files:**
- Modify: `templates/pendapatan/form.html`

Replace the single-tax section (tax_type, tax_account, tax_payment_account, tax fields — roughly lines 198–300) with a dynamic multi-tax container. Update the JS section.

- [ ] **Step 1: Replace the single-tax section in the Django template block**

  Find the block starting at (approximately):
  ```html
  <div class="ni-form-group ni-form-group--full">
    <label class="ni-form-label">
      Tipe Pajak
      <button type="button" class="tax-guide-toggle" ...>Panduan →</button>
    </label>
    {{ item_form.tax_type }}
    ...
  </div>
  <!-- through to the tax nominal field at line ~299 -->
  ```

  Replace the entire tax guide + 4 tax fields block with the new multi-tax container:

  ```html
  {# ── Pajak (Multiple Tax Lines) ───────────────────────────────────── #}
  <div class="ni-form-group ni-form-group--full">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
      <label class="ni-form-label" style="margin-bottom:0;">Baris Pajak</label>
      <button type="button" class="ni-btn ni-btn--xs ni-btn--secondary add-tax-btn">+ Tambah Pajak</button>
    </div>
    <p style="font-size:0.78rem;color:var(--ni-text-muted);margin:0 0 8px;">
      Satu baris = satu kewajiban pajak atas item ini. Contoh: PPN Keluaran + PPh 23 bisa diisi sekaligus.
    </p>
    <input type="hidden" name="item_0_tax_count" class="kp-tax-count" value="0">
    <div class="kp-tax-lines-cont"></div>
  </div>
  ```

  **Important:** The `name="item_0_tax_count"` will be reindexed by `reindexRows()` because it contains `item_0`. ✓

- [ ] **Step 2: Remove old tax-related JS from `attachRowEvents`**

  In the JS `attachRowEvents` function, remove the entire section that handles:
  - `tax-guide-panel`, `tax-guide-toggle`, `tax-guide-close` (lines ~607–643)
  - `taxTypeSel`, `taxAmtInp`, `taxBadge`, `taxLoadBadge`, `taxHint`, `taxUserEdited`, `doComputeTax`, and the `taxTypeSel.addEventListener('change', ...)` + `nilaiInp.addEventListener('input', ...)` blocks (lines ~645–714)

  Then add in their place, at the end of `attachRowEvents` (just before the "Remove button" section):

  ```javascript
  // ── Multi-tax: attach "Tambah Pajak" button ────────────────────────
  var addTaxBtn = row.querySelector('.add-tax-btn');
  if (addTaxBtn) {
    addTaxBtn.addEventListener('click', function () {
      addTaxLine(row);
    });
  }
  ```

- [ ] **Step 3: Add helper functions to the JS block**

  In the `(function () { ... })()` IIFE, before `attachRowEvents`, add:

  ```javascript
  // ── Account option extraction from rendered Django selects ────────────
  function getOptionsHtml(selector) {
    var src = document.querySelector(selector);
    if (!src) return '';
    return Array.from(src.options)
      .filter(function (o) { return o.value; })
      .map(function (o) {
        return '<option value="' + o.value + '">' +
          o.textContent.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') +
          '</option>';
      }).join('');
  }

  // ── Tax type select HTML (static, no Django rendering needed) ─────────
  var TAX_TYPE_OPTIONS = [
    ['ppn_keluaran', 'PPN Keluaran (11%)'],
    ['pph_23',       'PPh Pasal 23 (2%)'],
    ['pph_21',       'PPh Pasal 21 (Tenaga Ahli)'],
    ['pph_4_2',      'PPh Pasal 4(2) (Sewa 10%)'],
  ];

  function buildTaxTypeSelect(name, selectedValue) {
    var opts = '<option value="">— Pilih Tipe Pajak —</option>';
    TAX_TYPE_OPTIONS.forEach(function (p) {
      var sel = p[0] === selectedValue ? ' selected' : '';
      opts += '<option value="' + p[0] + '"' + sel + '>' + p[1] + '</option>';
    });
    return '<select name="' + name + '" class="ni-input kp-tax-type-sel">' + opts + '</select>';
  }

  function createTaxLineHtml(kpIdx, taxIdx, initial) {
    initial = initial || {};
    var prefix = 'item_' + kpIdx + '_tax_' + taxIdx;
    var allOpts = getOptionsHtml('[name$="-revenue_account"]');
    var assetOpts = getOptionsHtml('[name$="-payment_account"]');

    function makeSelect(name, optHtml, selected) {
      var opts = '<option value="">— Pilih —</option>' + optHtml;
      if (selected) {
        opts = opts.replace('value="' + selected + '"', 'value="' + selected + '" selected');
      }
      return '<select name="' + name + '" class="ni-input">' + opts + '</select>';
    }

    return (
      '<div class="kp-tax-line ni-mb-2" style="background:var(--ni-bg-subtle,#f9fafb);border:1px solid var(--ni-border,#e5e7eb);border-radius:8px;padding:12px;">' +
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">' +
          '<span style="font-size:0.78rem;font-weight:600;color:var(--ni-text-muted);">Baris Pajak ' + (taxIdx + 1) + '</span>' +
          '<button type="button" class="ni-btn ni-btn--xs ni-btn--danger kp-tax-remove-btn">✕</button>' +
        '</div>' +
        '<div class="ni-form-grid ni-form-grid--2">' +
          '<div class="ni-form-group ni-form-group--full">' +
            '<label class="ni-form-label" style="font-size:0.8rem;">Tipe Pajak</label>' +
            buildTaxTypeSelect(prefix + '_tax_type', initial.tax_type || '') +
          '</div>' +
          '<div class="ni-form-group">' +
            '<label class="ni-form-label" style="font-size:0.8rem;">Akun Pajak</label>' +
            makeSelect(prefix + '_tax_account', allOpts, initial.tax_account_id || '') +
          '</div>' +
          '<div class="ni-form-group">' +
            '<label class="ni-form-label" style="font-size:0.8rem;">Akun Lawan</label>' +
            makeSelect(prefix + '_tax_payment_account', assetOpts, initial.tax_payment_account_id || '') +
          '</div>' +
          '<div class="ni-form-group ni-form-group--full">' +
            '<label class="ni-form-label" style="font-size:0.8rem;">' +
              'Pajak (Nominal) ' +
              '<span class="tax-auto-badge" style="display:none;font-size:0.72rem;background:var(--ni-primary,#2563eb);color:#fff;padding:1px 6px;border-radius:999px;">Auto</span>' +
              '<span class="tax-loading-badge" style="display:none;font-size:0.72rem;color:var(--ni-text-muted);">Menghitung…</span>' +
            '</label>' +
            '<input type="number" name="' + prefix + '_tax" class="ni-input kp-tax-amt" step="0.01" value="' + (initial.tax || '') + '">' +
            '<span class="ni-help-text kp-tax-hint">Dihitung otomatis. Bisa diubah manual.</span>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function addTaxLine(row, initial) {
    var kpIdx = parseInt(row.getAttribute('data-index'));
    var countInp = row.querySelector('.kp-tax-count');
    var taxCont = row.querySelector('.kp-tax-lines-cont');
    var taxIdx = parseInt(countInp.value || '0');

    var div = document.createElement('div');
    div.innerHTML = createTaxLineHtml(kpIdx, taxIdx, initial);
    var newLine = div.firstElementChild;
    taxCont.appendChild(newLine);
    attachTaxLineEvents(newLine, row);
    countInp.value = taxIdx + 1;
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  function removeTaxLine(btn) {
    var line = btn.closest('.kp-tax-line');
    var row = line.closest('.ni-item-row');
    var taxCont = row.querySelector('.kp-tax-lines-cont');
    var countInp = row.querySelector('.kp-tax-count');
    line.remove();
    // Re-number remaining lines
    var kpIdx = parseInt(row.getAttribute('data-index'));
    taxCont.querySelectorAll('.kp-tax-line').forEach(function (l, j) {
      l.querySelectorAll('[name*="_tax_"]').forEach(function (el) {
        if (el.name) el.name = el.name.replace(/_tax_\d+_/, '_tax_' + j + '_');
      });
      var label = l.querySelector('span[style*="font-weight:600"]');
      if (label) label.textContent = 'Baris Pajak ' + (j + 1);
    });
    countInp.value = taxCont.querySelectorAll('.kp-tax-line').length;
  }

  function attachTaxLineEvents(line, row) {
    var typeSelect = line.querySelector('.kp-tax-type-sel');
    var amtInput   = line.querySelector('.kp-tax-amt');
    var autoBadge  = line.querySelector('.tax-auto-badge');
    var loadBadge  = line.querySelector('.tax-loading-badge');
    var hintEl     = line.querySelector('.kp-tax-hint');
    var nilaiInp   = row ? row.querySelector('[id$="-nilai_kontrak"]') : null;
    var userEdited = false;
    var timer = null;

    function doCompute() {
      if (!typeSelect || !typeSelect.value) return;
      if (!nilaiInp || !nilaiInp.value) return;
      var tanggalInp = document.getElementById('{{ form.tanggal.id_for_label }}');
      var tanggal = tanggalInp ? tanggalInp.value : '';
      var url = '/pajak/hitung/?tax_type=' + encodeURIComponent(typeSelect.value)
              + '&dpp=' + encodeURIComponent(nilaiInp.value)
              + (tanggal ? '&tanggal=' + encodeURIComponent(tanggal) : '');
      if (loadBadge) loadBadge.style.display = 'inline';
      if (autoBadge) autoBadge.style.display = 'none';
      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (loadBadge) loadBadge.style.display = 'none';
          if (d.error) { if (hintEl) hintEl.textContent = 'Tidak dapat menghitung: ' + d.error; return; }
          if (amtInput && !userEdited) {
            amtInput.value = d.jumlah_pajak;
            if (autoBadge) autoBadge.style.display = 'inline';
            if (hintEl) hintEl.textContent = d.tarif_persen + '% × DPP efektif Rp ' + parseFloat(d.dpp_efektif).toLocaleString('id-ID');
          }
        })
        .catch(function () { if (loadBadge) loadBadge.style.display = 'none'; });
    }

    if (typeSelect) {
      typeSelect.addEventListener('change', function () {
        userEdited = false;
        clearTimeout(timer);
        if (!typeSelect.value) { if (amtInput) amtInput.value = ''; return; }
        timer = setTimeout(doCompute, 300);
      });
    }
    if (nilaiInp) {
      nilaiInp.addEventListener('input', function () {
        if (!typeSelect || !typeSelect.value) return;
        userEdited = false;
        clearTimeout(timer);
        timer = setTimeout(doCompute, 500);
      });
    }
    if (amtInput) {
      amtInput.addEventListener('input', function () {
        userEdited = true;
        if (autoBadge) autoBadge.style.display = 'none';
        if (hintEl) hintEl.textContent = 'Nilai diubah manual.';
      });
    }
    // Remove button
    var removeBtn = line.querySelector('.kp-tax-remove-btn');
    if (removeBtn) removeBtn.addEventListener('click', function () { removeTaxLine(removeBtn); });

    // Auto-compute if values already present (edit mode)
    if (typeSelect && typeSelect.value && nilaiInp && nilaiInp.value && amtInput && amtInput.value) {
      if (autoBadge) autoBadge.style.display = 'inline';
      if (hintEl) hintEl.textContent = 'Nilai tersimpan sebelumnya.';
    }
  }
  ```

- [ ] **Step 4: Update `reindexRows` to also reindex tax count input and clear tax lines when cloning**

  The `reindexRows` function already handles `el.name.replace(/item_\d+/, 'item_' + i)` which covers `.kp-tax-count` input names like `item_0_tax_count` → `item_1_tax_count`. ✓

  In the `addBtn.addEventListener('click', ...)` block, after clearing recognition cards, add:

  ```javascript
  // Clear tax lines from the cloned row (each new KP starts with 0 tax lines)
  var taxCont = newRow.querySelector('.kp-tax-lines-cont');
  if (taxCont) taxCont.innerHTML = '';
  var taxCountInp = newRow.querySelector('.kp-tax-count');
  if (taxCountInp) taxCountInp.value = '0';
  ```

- [ ] **Step 5: Add tax lines population on page load (edit mode)**

  At the bottom of the IIFE (just before the closing `})();`), add:

  ```javascript
  // ── Populate tax lines from server data (edit mode) ───────────────────
  var taxLinesInitial = {{ tax_lines_initial_json|default:'{}' }};
  if (taxLinesInitial) {
    Object.keys(taxLinesInitial).forEach(function (kpIdxStr) {
      var kpIdx = parseInt(kpIdxStr);
      var row = container.querySelector('[data-index="' + kpIdx + '"]');
      if (!row) return;
      taxLinesInitial[kpIdxStr].forEach(function (tl) {
        addTaxLine(row, tl);
      });
    });
  }
  ```

- [ ] **Step 6: Manually smoke-test in browser**

  Start the dev server:
  ```powershell
  python manage.py runserver --settings=naveda_integra.settings.development
  ```
  - Navigate to create pendapatan page
  - Click "Tambah Pajak" on a KP row → tax line row appears with type select, akun dropdowns, amount
  - Select PPN Keluaran + fill nilai_kontrak → auto-calc should populate amount
  - Click "Tambah Pajak" again → second tax line (PPh 23) appears
  - Submit form → verify in admin/detail that 2 KPTaxLine objects exist for that KP
  - Navigate to edit → verify existing tax lines are pre-populated
  - Add new KP row → verify tax count is 0 and tax lines are empty for new row

- [ ] **Step 7: Commit**

  ```bash
  git add templates/pendapatan/form.html
  git commit -m "feat(pendapatan): multi-tax lines per KP in form — dynamic JS rows, auto-calc per line"
  ```

---

## Task 7: Update integration tests

**Files:**
- Modify: `apps/pajak/tests/test_pendapatan_integration.py`

The existing tests pass items dicts with `tax_type`, `tax`, `tax_account`, `tax_payment_account` at the top level. After the refactor, these must move into a `tax_lines` list.

- [ ] **Step 1: Update `_make_header_with_tax` helper**

  Replace:
  ```python
  items=[{
      'deskripsi_item': 'Konsultasi A',
      ...
      'tax_type': 'ppn_keluaran',
      'tax': Decimal('110000'),
      'tax_account': self.f['coa_ppn'],
      'tax_payment_account': self.f['coa_kas'],
  }],
  ```
  With:
  ```python
  items=[{
      'deskripsi_item': 'Konsultasi A',
      'kategori': 'jasa',
      'sub_transaction_type': self.f['stt'],
      'jumlah_bruto': Decimal('1000000'),
      'revenue_account': self.f['coa_revenue'],
      'payment_account': self.f['coa_kas'],
      'tax_lines': [{
          'tax_type': 'ppn_keluaran',
          'tax': Decimal('110000'),
          'tax_account': self.f['coa_ppn'],
          'tax_payment_account': self.f['coa_kas'],
      }],
  }],
  ```

- [ ] **Step 2: Update `_make_header_with_pph23` helper**

  Same pattern — wrap PPh 23 fields in `tax_lines`:
  ```python
  items=[{
      'deskripsi_item': 'Konsultasi PPh23',
      'kategori': 'jasa',
      'sub_transaction_type': self.f['stt'],
      'jumlah_bruto': Decimal('1000000'),
      'revenue_account': self.f['coa_revenue'],
      'payment_account': self.f['coa_kas'],
      'tax_lines': [{
          'tax_type': 'pph_23',
          'tax': Decimal('2000'),
          'tax_account': coa_pph23,
          'tax_payment_account': self.f['coa_kas'],
      }],
  }],
  ```

- [ ] **Step 3: Update `_make_confirmed_header_with_tax` in `VoidPendapatanTaxIntegrationTest`**

  Same pattern — wrap tax fields in `tax_lines`.

- [ ] **Step 4: Update `test_no_pajak_transaksi_when_no_tax_type`**

  That test creates an item WITHOUT tax fields; since we now use `tax_lines: []` (or omit), it stays the same — just ensure no `tax_lines` key means empty list (which `item.get('tax_lines', [])` handles). No change needed.

- [ ] **Step 5: Add dual-tax test (PPN + PPh 23 on one KP)**

  In `ConfirmPendapatanTaxIntegrationTest`, add:

  ```python
  def test_ppn_and_pph23_on_same_kp_creates_two_pajak_transaksi(self):
      """A KP with both PPN Keluaran and PPh 23 creates two PajakTransaksi records."""
      coa_pph23 = Akun.objects.create(
          kategori_id='aset', nama='PPh 23 Dibayar Dimuka', kode_akun='1.3.2',
      )
      header = create_pendapatan_header(
          tanggal=date(2026, 6, 1),
          deskripsi='Jasa dengan PPN + PPh 23',
          payment_type='cash',
          entitas_bisnis=self.f['eb'],
          payment_account=self.f['coa_kas'],
          items=[{
              'deskripsi_item': 'Jasa Dual Tax',
              'kategori': 'jasa',
              'sub_transaction_type': self.f['stt'],
              'jumlah_bruto': Decimal('1000000'),
              'revenue_account': self.f['coa_revenue'],
              'payment_account': self.f['coa_kas'],
              'tax_lines': [
                  {
                      'tax_type': 'ppn_keluaran',
                      'tax': Decimal('110000'),
                      'tax_account': self.f['coa_ppn'],
                      'tax_payment_account': self.f['coa_kas'],
                  },
                  {
                      'tax_type': 'pph_23',
                      'tax': Decimal('20000'),
                      'tax_account': coa_pph23,
                      'tax_payment_account': self.f['coa_kas'],
                  },
              ],
          }],
      )
      confirm_pendapatan(header, user=None)

      kp = header.entitas_groups.first().items.first()
      pajak_qs = PajakTransaksi.objects.filter(
          source_type='pendapatan_kp', source_id=kp.pk,
      )
      self.assertEqual(pajak_qs.count(), 2)
      jenis_list = sorted(pajak_qs.values_list('jenis_pajak', flat=True))
      self.assertIn('ppn_umum', jenis_list)
      self.assertIn('pph_23_jasa', jenis_list)

      ppn = pajak_qs.get(jenis_pajak='ppn_umum')
      self.assertEqual(ppn.jumlah_pajak, Decimal('110000'))
      self.assertEqual(ppn.status, 'final')

      pph = pajak_qs.get(jenis_pajak='pph_23_jasa')
      self.assertEqual(pph.jumlah_pajak, Decimal('20000'))
      self.assertEqual(pph.sifat_pajak, 'prepaid')
      self.assertEqual(pph.status, 'final')

  def test_void_cancels_all_tax_lines(self):
      """void_pendapatan cancels all PajakTransaksi for a dual-tax KP."""
      coa_pph23 = Akun.objects.create(
          kategori_id='aset', nama='PPh 23 Dimuka 2', kode_akun='1.3.3',
      )
      header = create_pendapatan_header(
          tanggal=date(2026, 6, 1),
          deskripsi='Dual tax void test',
          payment_type='cash',
          entitas_bisnis=self.f['eb'],
          payment_account=self.f['coa_kas'],
          items=[{
              'deskripsi_item': 'Jasa Dual Void',
              'kategori': 'jasa',
              'sub_transaction_type': self.f['stt'],
              'jumlah_bruto': Decimal('500000'),
              'revenue_account': self.f['coa_revenue'],
              'payment_account': self.f['coa_kas'],
              'tax_lines': [
                  {'tax_type': 'ppn_keluaran', 'tax': Decimal('55000'),
                   'tax_account': self.f['coa_ppn'], 'tax_payment_account': self.f['coa_kas']},
                  {'tax_type': 'pph_23', 'tax': Decimal('10000'),
                   'tax_account': coa_pph23, 'tax_payment_account': self.f['coa_kas']},
              ],
          }],
      )
      confirm_pendapatan(header, user=None)
      void_pendapatan(header, user=None)

      kp = header.entitas_groups.first().items.first()
      cancelled = PajakTransaksi.objects.filter(
          source_type='pendapatan_kp', source_id=kp.pk, status='dibatalkan',
      )
      self.assertEqual(cancelled.count(), 2)
  ```

- [ ] **Step 6: Run all tests — expect full pass**

  ```powershell
  python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
  ```

  Expected: All tests pass (including the 4 pre-existing piutang failures that are unrelated to this refactor — those are in `apps.piutang`).

- [ ] **Step 7: Commit**

  ```bash
  git add apps/pajak/tests/test_pendapatan_integration.py
  git commit -m "test(pajak): update integration tests for multi-tax KPTaxLine; add dual-tax test"
  ```

---

## Task 8: Update detail template for draft KPs

**Files:**
- Modify: `templates/pendapatan/detail.html`

Draft KPs don't have PajakTransaksi yet (created at confirm), but may have KPTaxLine records showing intent. Show them.

- [ ] **Step 1: Add tax_lines display in the KP detail block for draft status**

  In `templates/pendapatan/detail.html`, find where `kp.pajak_list` is shown (an amber box added in the previous session). That section shows actual PajakTransaksi. Add BEFORE that block, visible only when header is draft:

  ```html
  {% if header.status == 'draft' %}
    {% with kp.tax_lines.all as tlines %}
    {% if tlines %}
    <div style="margin-top:10px;padding:8px 12px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;font-size:0.8rem;">
      <p style="margin:0 0 6px;font-weight:600;color:#0369a1;">
        <i data-lucide="receipt" style="width:13px;height:13px;vertical-align:-2px;"></i>
        Baris Pajak ({{ tlines|length }} jenis — akan diproses saat konfirmasi)
      </p>
      {% for tl in tlines %}
      <div style="display:flex;gap:12px;padding:4px 0;border-bottom:1px solid #e0f2fe;{% if forloop.last %}border-bottom:none;{% endif %}">
        <span style="font-weight:500;">{{ tl.get_tax_type_display }}</span>
        {% if tl.tax %}
        <span>Override: Rp {{ tl.tax|floatformat:0 }}</span>
        {% else %}
        <span style="color:var(--ni-text-muted);">Auto (tarif berlaku)</span>
        {% endif %}
        <span style="color:var(--ni-text-muted);">→ {{ tl.tax_account.kode_akun }} / {{ tl.tax_payment_account.kode_akun }}</span>
      </div>
      {% endfor %}
    </div>
    {% endif %}
    {% endwith %}
  {% endif %}
  ```

- [ ] **Step 2: Update `pendapatan_detail` view prefetch_related**

  In `views.py`, update the `pendapatan_detail` prefetch_related to include tax lines for draft display:

  ```python
  header = get_object_or_404(
      PendapatanHeader.objects
      .select_related('created_by', 'source_recurring', 'source_sales')
      .prefetch_related(
          'entitas_groups__entitas_bisnis',
          'entitas_groups__payment_account',
          'entitas_groups__items__revenue_account',
          'entitas_groups__items__sub_transaction_type',
          'entitas_groups__items__tax_lines__tax_account',
          'entitas_groups__items__tax_lines__tax_payment_account',
          'entitas_groups__items__jadwal__entri__jurnal_header',
          'entitas_groups__items__aset_kontrak',
          'event_logs__actor',
      ),
      pk=pk,
  )
  ```

- [ ] **Step 3: Run tests + commit**

  ```powershell
  python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
  ```

  ```bash
  git add templates/pendapatan/detail.html apps/pendapatan/views.py
  git commit -m "feat(pendapatan): show KPTaxLine intent on draft detail page"
  ```

---

## Self-Review Checklist

- [x] `sync_pajak(override_amount=None)` — backward compatible; existing callers pass no kwarg → no change
- [x] `_cancel_kp_pajak` in services.py filters by `source_type='pendapatan_kp', source_id=kp.pk` — this queries PajakTransaksi, not KPTaxLine; works for multiple tax records per KP ✓
- [x] `pendapatan_hapus` in views.py deletes PajakTransaksi by source_type/source_id in a batch — unchanged logic; handles multiple records per KP ✓
- [x] `generate_from_recurring` in services.py creates a PendapatanItem without tax — no `tax_lines`, which is fine; `item.get('tax_lines', [])` returns `[]` ✓
- [x] `_create_pendapatan_journals` (legacy journal helper at bottom of services.py) updated in Task 3 Step 8
- [x] Migration's `RunPython` accesses `kp.tax_account_id` and `kp.tax_payment_account_id` before `RemoveField` — operations run in order, fields still exist when `RunPython` runs ✓
- [x] `reindexRows` JS regex `/item_\d+/` matches `item_0` in `item_0_tax_count` → `item_1_tax_count` ✓
- [x] Tax line name `item_0_tax_1_tax_type`: regex replaces first `item_0` → `item_1_tax_1_tax_type` ✓; `removeTaxLine` renumbers `_tax_\d+_` separately ✓
- [x] `TAX_PAYMENT_CHOICES` removal: only used by the removed `tax_payment` field; remove from models.py (grep first to verify)
