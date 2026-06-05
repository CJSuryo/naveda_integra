// Sample POS catalog — mirrors the Django data shape:
// item: { item_pk, name, kode_item, selling_price, category, modifier_groups[] }
// modifier_group: { pk, nama, is_required, min, max, options[] }
// option: { pk, name, additional_price, is_default }
//
// Prices in IDR (Rupiah). One store/outlet pre-selected.

window.POS_STORE = { name: 'Naveda Kopi', outlet: 'Outlet Senopati', cashier: 'Dewi A.' };

window.POS_CATEGORIES = [
  { id: 'all', label: 'Semua' },
  { id: 'kopi', label: 'Kopi' },
  { id: 'noncoffee', label: 'Non-Coffee' },
  { id: 'makanan', label: 'Makanan' },
  { id: 'pastry', label: 'Pastry' },
  { id: 'retail', label: 'Retail' },
];

// Shared modifier groups
const G_SIZE = {
  pk: 1, nama: 'Ukuran', is_required: true, min: 1, max: 1,
  options: [
    { pk: 11, name: 'Regular', additional_price: 0, is_default: true },
    { pk: 12, name: 'Large', additional_price: 6000, is_default: false },
  ],
};
const G_MILK = {
  pk: 2, nama: 'Pilihan Susu', is_required: false, min: 0, max: 1,
  options: [
    { pk: 21, name: 'Susu Sapi', additional_price: 0, is_default: true },
    { pk: 22, name: 'Oat Milk', additional_price: 8000, is_default: false },
    { pk: 23, name: 'Almond Milk', additional_price: 8000, is_default: false },
  ],
};
const G_SUGAR = {
  pk: 3, nama: 'Tingkat Gula', is_required: true, min: 1, max: 1,
  options: [
    { pk: 31, name: 'Normal', additional_price: 0, is_default: true },
    { pk: 32, name: 'Less Sugar', additional_price: 0, is_default: false },
    { pk: 33, name: 'No Sugar', additional_price: 0, is_default: false },
  ],
};
const G_TEMP = {
  pk: 4, nama: 'Suhu', is_required: true, min: 1, max: 1,
  options: [
    { pk: 41, name: 'Hot', additional_price: 0, is_default: true },
    { pk: 42, name: 'Iced', additional_price: 3000, is_default: false },
  ],
};
const G_EXTRA = {
  pk: 5, nama: 'Extra', is_required: false, min: 0, max: 3,
  options: [
    { pk: 51, name: 'Extra Shot', additional_price: 7000, is_default: false },
    { pk: 52, name: 'Caramel Syrup', additional_price: 5000, is_default: false },
    { pk: 53, name: 'Whipped Cream', additional_price: 5000, is_default: false },
  ],
};

window.POS_ITEMS = [
  // Kopi
  { item_pk: 101, name: 'Kopi Susu Naveda', kode_item: 'KOP-001', selling_price: 28000, category: 'kopi', modifier_groups: [G_SIZE, G_TEMP, G_SUGAR, G_EXTRA] },
  { item_pk: 102, name: 'Es Kopi Gula Aren', kode_item: 'KOP-002', selling_price: 30000, category: 'kopi', modifier_groups: [G_SIZE, G_SUGAR, G_EXTRA] },
  { item_pk: 103, name: 'Americano', kode_item: 'KOP-003', selling_price: 25000, category: 'kopi', modifier_groups: [G_SIZE, G_TEMP] },
  { item_pk: 104, name: 'Cappuccino', kode_item: 'KOP-004', selling_price: 32000, category: 'kopi', modifier_groups: [G_SIZE, G_MILK, G_TEMP, G_EXTRA] },
  { item_pk: 105, name: 'Caffè Latte', kode_item: 'KOP-005', selling_price: 32000, category: 'kopi', modifier_groups: [G_SIZE, G_MILK, G_TEMP, G_EXTRA] },
  { item_pk: 106, name: 'Espresso', kode_item: 'KOP-006', selling_price: 22000, category: 'kopi', modifier_groups: [] },
  { item_pk: 107, name: 'Magic Coffee', kode_item: 'KOP-007', selling_price: 35000, category: 'kopi', modifier_groups: [G_MILK, G_EXTRA] },
  { item_pk: 108, name: 'Kopi Pandan', kode_item: 'KOP-008', selling_price: 33000, category: 'kopi', modifier_groups: [G_SIZE, G_SUGAR] },

  // Non-Coffee
  { item_pk: 201, name: 'Matcha Latte', kode_item: 'NCF-001', selling_price: 34000, category: 'noncoffee', modifier_groups: [G_SIZE, G_MILK, G_TEMP, G_SUGAR] },
  { item_pk: 202, name: 'Cokelat Klasik', kode_item: 'NCF-002', selling_price: 30000, category: 'noncoffee', modifier_groups: [G_SIZE, G_TEMP, G_SUGAR] },
  { item_pk: 203, name: 'Teh Tarik', kode_item: 'NCF-003', selling_price: 26000, category: 'noncoffee', modifier_groups: [G_SIZE, G_SUGAR] },
  { item_pk: 204, name: 'Lemon Tea', kode_item: 'NCF-004', selling_price: 24000, category: 'noncoffee', modifier_groups: [G_SIZE, G_TEMP] },
  { item_pk: 205, name: 'Strawberry Yakult', kode_item: 'NCF-005', selling_price: 32000, category: 'noncoffee', modifier_groups: [G_SIZE] },
  { item_pk: 206, name: 'Es Kelapa Jeruk', kode_item: 'NCF-006', selling_price: 28000, category: 'noncoffee', modifier_groups: [] },

  // Makanan
  { item_pk: 301, name: 'Nasi Ayam Geprek', kode_item: 'MKN-001', selling_price: 38000, category: 'makanan', modifier_groups: [{ pk: 6, nama: 'Level Pedas', is_required: true, min: 1, max: 1, options: [ { pk: 61, name: 'Level 1', additional_price: 0, is_default: true }, { pk: 62, name: 'Level 3', additional_price: 0, is_default: false }, { pk: 63, name: 'Level 5', additional_price: 0, is_default: false } ] }] },
  { item_pk: 302, name: 'Spaghetti Aglio Olio', kode_item: 'MKN-002', selling_price: 45000, category: 'makanan', modifier_groups: [] },
  { item_pk: 303, name: 'Chicken Caesar Salad', kode_item: 'MKN-003', selling_price: 42000, category: 'makanan', modifier_groups: [] },
  { item_pk: 304, name: 'Beef Slider (2 pcs)', kode_item: 'MKN-004', selling_price: 48000, category: 'makanan', modifier_groups: [] },
  { item_pk: 305, name: 'French Fries', kode_item: 'MKN-005', selling_price: 25000, category: 'makanan', modifier_groups: [{ pk: 7, nama: 'Saus', is_required: false, min: 0, max: 2, options: [ { pk: 71, name: 'Mayo', additional_price: 0, is_default: false }, { pk: 72, name: 'BBQ', additional_price: 0, is_default: false }, { pk: 73, name: 'Cheese', additional_price: 6000, is_default: false } ] }] },
  { item_pk: 306, name: 'Roti Bakar Cokelat', kode_item: 'MKN-006', selling_price: 27000, category: 'makanan', modifier_groups: [] },

  // Pastry
  { item_pk: 401, name: 'Butter Croissant', kode_item: 'PST-001', selling_price: 26000, category: 'pastry', modifier_groups: [] },
  { item_pk: 402, name: 'Pain au Chocolat', kode_item: 'PST-002', selling_price: 29000, category: 'pastry', modifier_groups: [] },
  { item_pk: 403, name: 'Cinnamon Roll', kode_item: 'PST-003', selling_price: 30000, category: 'pastry', modifier_groups: [] },
  { item_pk: 404, name: 'Banana Bread', kode_item: 'PST-004', selling_price: 28000, category: 'pastry', modifier_groups: [] },
  { item_pk: 405, name: 'Cheese Tart', kode_item: 'PST-005', selling_price: 24000, category: 'pastry', modifier_groups: [] },

  // Retail (beans, merch)
  { item_pk: 501, name: 'Beans Arabica 250g', kode_item: 'RTL-001', selling_price: 95000, category: 'retail', modifier_groups: [] },
  { item_pk: 502, name: 'Beans House Blend 1kg', kode_item: 'RTL-002', selling_price: 320000, category: 'retail', modifier_groups: [] },
  { item_pk: 503, name: 'Tumbler Naveda', kode_item: 'RTL-003', selling_price: 150000, category: 'retail', modifier_groups: [] },
  { item_pk: 504, name: 'Tote Bag Kanvas', kode_item: 'RTL-004', selling_price: 85000, category: 'retail', modifier_groups: [] },
  { item_pk: 505, name: 'Drip Bag (5 pcs)', kode_item: 'RTL-005', selling_price: 60000, category: 'retail', modifier_groups: [] },
];

// PPN (Indonesian VAT) rate applied to subtotal
window.POS_TAX_RATE = 0.11;

// Pre-seeded held bills for the tray demo
window.POS_HELD_SEED = [
  { id: 'HOLD-01', label: 'Meja 4', count: 3, total: 96000, time: '14:02' },
  { id: 'HOLD-02', label: 'Take Away — Budi', count: 2, total: 58000, time: '14:11' },
];

// Currency helper
window.rp = function (n) {
  n = Math.round(Number(n) || 0);
  return 'Rp\u00a0' + n.toLocaleString('id-ID');
};
