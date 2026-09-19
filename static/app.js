const api = (path, options = {}) => fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options }).then(async response => {
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "خطا در ارتباط با برنامه");
  return data;
});

const currency = value => `${Number(value || 0).toLocaleString("fa-IR")} تومان`;
const statusLabel = { paid: "پرداخت‌شده", partial: "پرداخت جزئی", overdue: "معوق", unpaid: "پرداخت‌نشده" };
const jalaliMonths = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
let accounts = [], categories = [], currentInstallments = [];

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const formatDate = value => value;
const latinDigits = value => String(value).replace(/[۰-۹]/g, digit => "۰۱۲۳۴۵۶۷۸۹".indexOf(digit));
const persianDigits = value => String(value).replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[digit]);
function currentJalaliParts() {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  return Object.fromEntries(parts.filter(part => ["year", "month", "day"].includes(part.type)).map(part => [part.type, Number(part.value)]));
}
function jalaliMonthKey(year, month) { return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}`; }
function offsetJalaliMonth(year, month, offset) { const index = year * 12 + (month - 1) + offset; return { year: Math.floor(index / 12), month: (index % 12) + 1 }; }
function jalaliMonthLabel(key) { const [year, month] = key.split("-").map(Number); return `${jalaliMonths[month - 1]} ${persianDigits(year)}`; }
function populateMonthSelectors() {
  const now = currentJalaliParts();
  const current = jalaliMonthKey(now.year, now.month);
  const options = Array.from({ length: 37 }, (_, index) => {
    const item = offsetJalaliMonth(now.year, now.month, index - 12);
    const key = jalaliMonthKey(item.year, item.month);
    return `<option value="${key}">${jalaliMonthLabel(key)}</option>`;
  }).join("");
  ["dashboardMonth", "transactionMonth", "installmentMonth"].forEach(id => {
    document.getElementById(id).innerHTML = options;
    document.getElementById(id).value = current;
  });
}
function setJalaliDateDefaults() {
  const now = currentJalaliParts();
  const today = `${persianDigits(now.year.toString().padStart(4, "0"))}/${persianDigits(now.month.toString().padStart(2, "0"))}/${persianDigits(now.day.toString().padStart(2, "0"))}`;
  const followingMonth = offsetJalaliMonth(now.year, now.month, 1);
  document.getElementById("transactionDate").value = today;
  document.getElementById("paymentDate").value = today;
  document.getElementById("firstDueDate").value = `${persianDigits(followingMonth.year.toString().padStart(4, "0"))}/${persianDigits(followingMonth.month.toString().padStart(2, "0"))}/۰۱`;
}
function setMessage(id, message, error = false) { const node = document.getElementById(id); node.textContent = message; node.classList.toggle("error", error); }
function optionMarkup(items, label = item => item.name) { return items.map(item => `<option value="${item.id}">${escapeHtml(label(item))}</option>`).join(""); }
function renderRows(id, cells, colspan) { const target = document.getElementById(id); target.innerHTML = cells.length ? cells.join("") : `<tr><td colspan="${colspan}" class="empty-cell">هنوز داده‌ای ثبت نشده است.</td></tr>`; }

async function loadReferenceData() {
  [accounts, categories] = await Promise.all([api("/accounts"), api("/categories")]);
  const accountOptions = `<option value="">انتخاب نشده</option>${optionMarkup(accounts)}`;
  document.getElementById("transactionAccount").innerHTML = accountOptions;
  document.getElementById("paymentAccount").innerHTML = accountOptions;
  updateCategories();
}

function updateCategories() {
  const type = document.getElementById("transactionType").value;
  const matched = categories.filter(category => category.transaction_type === type);
  document.getElementById("transactionCategory").innerHTML = optionMarkup(matched);
}

async function loadDashboard() {
  const month = document.getElementById("dashboardMonth").value;
  const data = await api(`/dashboard?month=${month}`);
  document.getElementById("incomeValue").textContent = currency(data.income);
  document.getElementById("expenseValue").textContent = currency(data.expense);
  document.getElementById("remainingValue").textContent = currency(data.remaining_commitments);
  document.getElementById("overdueValue").textContent = currency(data.overdue_commitments);
  document.getElementById("plannedValue").textContent = currency(data.planned_commitments);
  document.getElementById("paidValue").textContent = currency(data.paid_commitments);
  document.getElementById("commitmentSummary").textContent = `${data.month_label} · ${data.upcoming.length} سررسید باز`;
  document.getElementById("commitmentProgress").style.width = data.planned_commitments ? `${Math.min(100, (data.paid_commitments / data.planned_commitments) * 100)}%` : "0%";
  const upcoming = data.upcoming.map(item => `<div class="list-item"><div><b>${escapeHtml(item.title)}</b><small>${formatDate(item.due_date)} · ${statusLabel[item.status]}</small></div><strong>${currency(item.remaining_amount)}</strong></div>`);
  document.getElementById("upcomingList").classList.toggle("empty", !upcoming.length);
  document.getElementById("upcomingList").innerHTML = upcoming.length ? upcoming.join("") : "موردی برای نمایش نیست.";
}

async function loadTransactions() {
  const month = document.getElementById("transactionMonth").value;
  const data = await api(`/transactions?month=${month}`);
  renderRows("transactionRows", data.map(item => `<tr><td>${formatDate(item.occurred_on)}</td><td>${escapeHtml(item.note || "—")}</td><td>${escapeHtml(item.category_name || "—")}</td><td><span class="badge ${item.transaction_type === "expense" ? "partial" : ""}">${item.transaction_type === "expense" ? "هزینه" : "درآمد"}</span></td><td>${currency(item.amount)}</td></tr>`), 5);
}

async function loadInstallments() {
  const month = document.getElementById("installmentMonth").value;
  currentInstallments = await api(`/installments?month=${month}`);
  renderRows("installmentRows", currentInstallments.map(item => `<tr><td>${escapeHtml(item.title)}</td><td>${formatDate(item.due_date)}</td><td>${currency(item.amount)}</td><td>${currency(item.paid_amount)}</td><td>${currency(item.remaining_amount)}</td><td><span class="badge ${item.status}">${statusLabel[item.status]}</span></td></tr>`), 6);
  const openItems = currentInstallments.filter(item => item.remaining_amount > 0);
  document.getElementById("paymentInstallment").innerHTML = openItems.length ? openItems.map(item => `<option value="${item.id}" data-remaining="${item.remaining_amount}">${escapeHtml(item.title)} — ${formatDate(item.due_date)} (مانده ${currency(item.remaining_amount)})</option>`).join("") : `<option value="">سررسید باز وجود ندارد</option>`;
  if (openItems.length) document.getElementById("paymentAmount").value = openItems[0].remaining_amount;
}

async function refreshAll() { await Promise.all([loadDashboard(), loadTransactions(), loadInstallments()]); }

async function loadReleases() {
  const releases = await api("/releases");
  document.getElementById("releaseList").innerHTML = releases.length ? releases.map(item => `<article class="release-item"><h2>نگارش ${escapeHtml(item.version)} — ${escapeHtml(item.title)}</h2><p class="release-meta">${escapeHtml(item.released_at)} · بخش‌های تحت تأثیر: ${escapeHtml(item.affected_areas)}</p><p>${escapeHtml(item.description)}</p></article>`).join("") : "<p>تاریخچه‌ای ثبت نشده است.</p>";
}

document.querySelectorAll(".nav-link,[data-page]").forEach(button => button.addEventListener("click", () => {
  const page = button.dataset.page;
  if (!page) return;
  document.querySelectorAll(".page").forEach(section => section.classList.toggle("active", section.id === page));
  document.querySelectorAll(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.page === page));
}));

document.getElementById("transactionType").addEventListener("change", updateCategories);
document.getElementById("dashboardMonth").addEventListener("change", loadDashboard);
document.getElementById("transactionMonth").addEventListener("change", loadTransactions);
document.getElementById("installmentMonth").addEventListener("change", loadInstallments);
document.getElementById("paymentInstallment").addEventListener("change", event => { const option = event.target.selectedOptions[0]; if (option) document.getElementById("paymentAmount").value = option.dataset.remaining || ""; });

document.getElementById("transactionForm").addEventListener("submit", async event => {
  event.preventDefault(); setMessage("transactionMessage", "");
  try {
    await api("/transactions", { method: "POST", body: JSON.stringify({ transaction_type: document.getElementById("transactionType").value, amount: Number(document.getElementById("transactionAmount").value), occurred_on: document.getElementById("transactionDate").value, category_id: Number(document.getElementById("transactionCategory").value), account_id: Number(document.getElementById("transactionAccount").value) || null, note: document.getElementById("transactionNote").value }) });
    event.target.reset(); setJalaliDateDefaults(); updateCategories(); setMessage("transactionMessage", "تراکنش ثبت شد."); await refreshAll();
  } catch (error) { setMessage("transactionMessage", error.message, true); }
});

document.getElementById("commitmentForm").addEventListener("submit", async event => {
  event.preventDefault(); setMessage("commitmentMessage", "");
  try {
    await api("/commitments", { method: "POST", body: JSON.stringify({ title: document.getElementById("commitmentTitle").value, kind: document.getElementById("commitmentKind").value, total_amount: Number(document.getElementById("commitmentTotal").value) || null, installment_amount: Number(document.getElementById("installmentAmount").value), first_due_date: document.getElementById("firstDueDate").value, installment_count: Number(document.getElementById("installmentCount").value) }) });
    event.target.reset(); setJalaliDateDefaults(); document.getElementById("installmentCount").value = 12; setMessage("commitmentMessage", "برنامهٔ پرداخت ایجاد شد."); await refreshAll();
  } catch (error) { setMessage("commitmentMessage", error.message, true); }
});

document.getElementById("paymentForm").addEventListener("submit", async event => {
  event.preventDefault(); setMessage("paymentMessage", "");
  try {
    await api("/payments", { method: "POST", body: JSON.stringify({ installment_id: Number(document.getElementById("paymentInstallment").value), amount: Number(document.getElementById("paymentAmount").value), paid_on: document.getElementById("paymentDate").value, account_id: Number(document.getElementById("paymentAccount").value) || null, note: "" }) });
    setMessage("paymentMessage", "پرداخت ثبت شد."); await refreshAll();
  } catch (error) { setMessage("paymentMessage", error.message, true); }
});

populateMonthSelectors();
setJalaliDateDefaults();
loadReferenceData().then(async () => { await refreshAll(); await loadReleases(); }).catch(error => document.body.insertAdjacentHTML("afterbegin", `<p class="fatal" role="alert">${escapeHtml(error.message)}</p>`));
