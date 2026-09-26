const api = (path, options = {}) => fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options }).then(async response => {
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "خطا در ارتباط با برنامه");
  return data;
});

const currency = value => `${Number(value || 0).toLocaleString("fa-IR")} تومان`;
const statusLabel = { paid: "پرداخت‌شده", partial: "پرداخت جزئی", overdue: "معوق", unpaid: "پرداخت‌نشده" };
const jalaliMonths = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
let accounts = [], categories = [], commitmentFilters = [], commitmentList = [], currentInstallments = [], baseInstallments = [], commitmentPreview = null;
let commitmentSort = { key: "distance_days", direction: "asc" };
const currentCommitmentMonth = currentJalaliParts();
let commitmentGridFilters = {
  title: new Set(), kind: new Set(), year: new Set([String(currentCommitmentMonth.year)]),
  month: new Set([String(currentCommitmentMonth.month)]), status: new Set()
};
const commitmentStatusNames = { settled: "تسویه‌شده", partial: "پرداخت جزئی", unpaid: "پرداخت‌نشده" };
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const persianDigits = value => String(value).replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[digit]);
const latinDigits = value => String(value).replace(/[۰-۹]/g, digit => "۰۱۲۳۴۵۶۷۸۹".indexOf(digit)).replace(/[٠-٩]/g, digit => "٠١٢٣٤٥٦٧٨٩".indexOf(digit));
const amountNumber = value => Number(latinDigits(value).replace(/[٬,\s]/g, "")) || 0;
function auditText(value) {
  if (typeof value === "string") return value.replace(/\b\d{4}-\d{2}-\d{2}\b/g, date => {
    const formatted = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(`${date}T12:00:00`));
    return formatted;
  });
  return auditText(JSON.stringify(value));
}

function currentJalaliParts() {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  return Object.fromEntries(parts.filter(part => ["year", "month", "day"].includes(part.type)).map(part => [part.type, Number(part.value)]));
}
function jalaliMonthKey(year, month) { return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}`; }
function offsetJalaliMonth(year, month, offset) { const index = year * 12 + month - 1 + offset; return { year: Math.floor(index / 12), month: index % 12 + 1 }; }
function jalaliMonthLabel(key) { const [year, month] = key.split("-").map(Number); return `${jalaliMonths[month - 1]} ${persianDigits(year)}`; }
function todayJalali() { const now = currentJalaliParts(); return `${persianDigits(String(now.year).padStart(4, "0"))}/${persianDigits(String(now.month).padStart(2, "0"))}/${persianDigits(String(now.day).padStart(2, "0"))}`; }
function setMessage(id, message, error = false) { const node = document.getElementById(id); node.textContent = message; node.classList.toggle("error", error); }
function renderRows(id, rows, colspan) { document.getElementById(id).innerHTML = rows.length ? rows.join("") : `<tr><td colspan="${colspan}" class="empty-cell">داده‌ای برای نمایش نیست.</td></tr>`; }
function accountOptions() { return `<option value="">حساب انتخاب نشده</option>${accounts.map(account => `<option value="${account.id}">${escapeHtml(account.name)}</option>`).join("")}`; }
function formatAmountInput(input) { const amount = amountNumber(input.value); input.value = amount ? amount.toLocaleString("fa-IR") : ""; }

function populateMonthSelectors() {
  const now = currentJalaliParts(); const current = jalaliMonthKey(now.year, now.month);
  const options = Array.from({ length: 37 }, (_, index) => { const item = offsetJalaliMonth(now.year, now.month, index - 12); const key = jalaliMonthKey(item.year, item.month); return `<option value="${key}">${jalaliMonthLabel(key)}</option>`; }).join("");
  document.getElementById("dashboardMonth").innerHTML = options;
  document.getElementById("transactionMonth").innerHTML = options;
  document.getElementById("installmentMonth").innerHTML = `<option value="">همهٔ ماه‌ها</option>${options}`;
  document.getElementById("dashboardMonth").value = current;
  document.getElementById("transactionMonth").value = current;
  document.getElementById("installmentMonth").value = current;
}
function setJalaliDateDefaults() {
  const now = currentJalaliParts(); const next = offsetJalaliMonth(now.year, now.month, 1);
  document.getElementById("transactionDate").value = todayJalali();
  document.getElementById("firstDueDate").value = `${persianDigits(String(next.year).padStart(4, "0"))}/${persianDigits(String(next.month).padStart(2, "0"))}/۰۱`;
}

async function loadReferenceData() {
  [accounts, categories, commitmentFilters, commitmentList] = await Promise.all([api("/accounts"), api("/categories"), api("/commitment-filters"), api("/commitments")]);
  document.getElementById("transactionAccount").innerHTML = accountOptions();
  document.getElementById("installmentCommitment").innerHTML = `<option value="">همهٔ تعهدات</option>${commitmentFilters.map(item => `<option value="${escapeHtml(JSON.stringify([item.title, item.total_amount]))}">${escapeHtml(item.title)}${item.total_amount === null ? "" : ` (${currency(item.total_amount)})`}</option>`).join("")}`;
  renderCommitmentGrid();
  updateCategories();
}
function updateCategories() { const type = document.getElementById("transactionType").value; document.getElementById("transactionCategory").innerHTML = categories.filter(item => item.transaction_type === type).map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join(""); }
function commitmentDisplay(item) {
  const status = item.installment_count > 0 && item.paid_amount >= item.planned_amount ? "settled" : item.paid_amount > 0 ? "partial" : "unpaid";
  const dueDate = item.next_unpaid_due_date || item.last_due_date;
  const today = new Date();
  const days = dueDate ? Math.round((Date.parse(`${dueDate}T00:00:00Z`) - Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000) : null;
  const distance = days === null ? "—" : days === 0 ? "امروز" : days > 0 ? `${persianDigits(days)} روز مانده` : `${persianDigits(-days)} روز گذشته`;
  return { ...item, status, distance_days: days, distance };
}
function groupedCommitments() {
  const groups = new Map();
  for (const item of commitmentList) {
    const key = item.title.trim().replace(/\s+/g, " ").replace(/ي/g, "ی").replace(/ك/g, "ک");
    if (!groups.has(key)) groups.set(key, { ...item, title: key, members: [], installment_count: 0, planned_amount: 0, paid_amount: 0, total_amount: 0, next_unpaid_due_date: null, last_due_date: null, kinds: new Set() });
    const group = groups.get(key);
    group.members.push(item);
    group.kinds.add(item.kind);
    group.dueDates ??= new Set();
    for (const due of (item.due_dates || "").split(",")) if (due) group.dueDates.add(due);
    group.installment_count += item.installment_count;
    group.planned_amount += item.planned_amount;
    group.paid_amount += item.paid_amount;
    if (item.total_amount != null) group.total_amount += item.total_amount;
    if (item.next_unpaid_due_date && (!group.next_unpaid_due_date || item.next_unpaid_due_date < group.next_unpaid_due_date)) group.next_unpaid_due_date = item.next_unpaid_due_date;
    if (item.last_due_date && (!group.last_due_date || item.last_due_date > group.last_due_date)) group.last_due_date = item.last_due_date;
  }
  return [...groups.values()].map(group => ({ ...group, kind: [...group.kinds].join("، "), total_amount: group.members.some(item => item.total_amount != null) ? group.total_amount : null }));
}
function commitmentDueMonths(item) {
  return [...item.dueDates].map(iso => {
    const parts = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "numeric" }).formatToParts(new Date(`${iso}T12:00:00Z`));
    const value = Object.fromEntries(parts.filter(part => part.type === "year" || part.type === "month").map(part => [part.type, Number(part.value)]));
    return { year: String(value.year), month: String(value.month) };
  });
}
function matchesCommitmentFilters(item, excluded = null) {
  const selected = commitmentGridFilters;
  if (excluded !== "title" && selected.title.size && !selected.title.has(item.title)) return false;
  if (excluded !== "kind" && selected.kind.size && ![...item.kinds].some(kind => selected.kind.has(kind))) return false;
  if (excluded !== "status" && selected.status.size && !selected.status.has(item.status)) return false;
  const years = excluded === "year" ? null : selected.year;
  const months = excluded === "month" ? null : selected.month;
  if ((!years || !years.size) && (!months || !months.size)) return true;
  return item.months.some(due => (!years || !years.size || years.has(due.year)) && (!months || !months.size || months.has(due.month)));
}
function renderCommitmentFilters(items) {
  const allLabels = { title: "همه عنوان‌ها", kind: "همه انواع", year: "همه سال‌ها", month: "همه ماه‌ها", status: "همه وضعیت‌ها" };
  const allYears = [...new Set(items.flatMap(item => item.months.map(due => due.year)))].sort((a, b) => Number(a) - Number(b));
  for (const filter of Object.keys(commitmentGridFilters)) {
    const facet = document.querySelector(`#commitmentGridFilters [data-filter="${filter}"]`);
    const candidates = items.filter(item => matchesCommitmentFilters(item, filter));
    const available = new Set(candidates.flatMap(item => filter === "title" ? [item.title] : filter === "kind" ? [...item.kinds] : filter === "status" ? [item.status] : item.months.map(due => due[filter])));
    const values = filter === "year" ? allYears : filter === "month" ? Array.from({ length: 12 }, (_, index) => String(index + 1)) : [...new Set(items.flatMap(item => filter === "title" ? [item.title] : filter === "kind" ? [...item.kinds] : [item.status]))].sort((a, b) => a.localeCompare(b, "fa"));
    const selected = commitmentGridFilters[filter];
    facet.querySelector("summary").textContent = selected.size ? [...selected].map(value => filter === "month" ? jalaliMonths[Number(value) - 1] : filter === "year" ? persianDigits(value) : filter === "status" ? commitmentStatusNames[value] : value).join("، ") : allLabels[filter];
    facet.querySelector(".facet-options").innerHTML = `<label><input type="checkbox" value="" ${selected.size ? "" : "checked"} />${allLabels[filter]}</label>${values.filter(value => filter === "year" || filter === "month" || available.has(value) || selected.has(value)).map(value => `<label><input type="checkbox" value="${escapeHtml(value)}" ${selected.has(value) ? "checked" : ""} ${!available.has(value) && !selected.has(value) ? "disabled" : ""} />${escapeHtml(filter === "month" ? jalaliMonths[Number(value) - 1] : filter === "year" ? persianDigits(value) : filter === "status" ? commitmentStatusNames[value] : value)}</label>`).join("")}`;
  }
}
function renderCommitmentGrid() {
  const groups = groupedCommitments().map(item => ({ ...commitmentDisplay(item), months: commitmentDueMonths(item) }));
  renderCommitmentFilters(groups);
  const items = groups.filter(item => matchesCommitmentFilters(item));
  const { key, direction } = commitmentSort;
  items.sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null || y == null) return x == null && y == null ? a.id - b.id : x == null ? 1 : -1;
    const comparison = typeof x === "string" ? x.localeCompare(y, "fa") : x - y;
    return (direction === "asc" ? comparison : -comparison) || a.id - b.id;
  });
  document.querySelectorAll(".commitment-grid-panel th[data-sort]").forEach(th => {
    const active = th.dataset.sort === key;
    th.setAttribute("aria-sort", active ? direction === "asc" ? "ascending" : "descending" : "none");
    th.classList.toggle("sort-active", active);
    th.querySelector(".sort-indicator")?.remove();
    if (active) th.insertAdjacentHTML("beforeend", `<span class="sort-indicator" aria-hidden="true"> ${direction === "asc" ? "▲" : "▼"}</span>`);
  });
  renderRows("commitmentRows", items.map(item => `<tr class="commitment-${item.status}"><td>${escapeHtml(item.title)}</td><td>${escapeHtml(item.kind)}</td><td>${item.total_amount ? currency(item.total_amount) : "—"}</td><td>${persianDigits(item.installment_count)}</td><td>${currency(item.planned_amount)}</td><td>${currency(item.paid_amount)}</td><td><span class="badge ${item.status}">${item.status === "settled" ? "تسویه‌شده" : item.status === "partial" ? "پرداخت جزئی" : "پرداخت‌نشده"}</span></td><td>${item.distance}</td><td><button class="quiet edit-grid-group" data-id="${item.id}">ویرایش تعهد</button>${item.members.length > 1 ? `<button class="quiet view-group-details" data-title="${escapeHtml(item.title)}">جزئیات</button>` : ""}</td></tr>`), 9);
}

async function loadDashboard() {
  const data = await api(`/dashboard?month=${document.getElementById("dashboardMonth").value}`);
  [["incomeValue", data.income], ["expenseValue", data.expense], ["remainingValue", data.remaining_commitments], ["overdueValue", data.overdue_commitments], ["plannedValue", data.planned_commitments], ["paidValue", data.paid_commitments]].forEach(([id, value]) => document.getElementById(id).textContent = currency(value));
  document.getElementById("commitmentSummary").textContent = `${data.month_label} · ${persianDigits(data.upcoming.length)} سررسید باز`;
  document.getElementById("commitmentProgress").style.width = data.planned_commitments ? `${Math.min(100, data.paid_commitments / data.planned_commitments * 100)}%` : "0%";
  const rows = data.upcoming.map(item => `<div class="list-item"><div><b>${escapeHtml(item.title)}</b><small>${item.due_date} · ${statusLabel[item.status]}</small></div><strong>${currency(item.remaining_amount)}</strong></div>`);
  document.getElementById("upcomingList").innerHTML = rows.length ? rows.join("") : "موردی برای نمایش نیست.";
}
async function loadTransactions() {
  const data = await api(`/transactions?month=${document.getElementById("transactionMonth").value}`);
  renderRows("transactionRows", data.map(item => `<tr><td>${item.occurred_on}</td><td>${escapeHtml(item.note || "—")}</td><td>${escapeHtml(item.category_name || "—")}</td><td><span class="badge ${item.transaction_type === "expense" ? "partial" : ""}">${item.transaction_type === "expense" ? "هزینه" : "درآمد"}</span></td><td>${currency(item.amount)}</td></tr>`), 5);
}
function installmentQuery(includeStatus = false) {
  const params = new URLSearchParams();
  [["month", "installmentMonth"], ["search", "installmentSearch"]].forEach(([key, id]) => { const value = document.getElementById(id).value.trim(); if (value) params.set(key, value); });
  if (includeStatus && document.getElementById("installmentStatus").value) params.set("status", document.getElementById("installmentStatus").value);
  const filterValue = document.getElementById("installmentCommitment").value;
  if (filterValue) {
    const [title, total] = JSON.parse(filterValue);
    params.set("commitment_title", title);
    if (total === null) params.set("commitment_total_missing", "true");
    else params.set("commitment_total", total);
  }
  return params.toString();
}

function updateStatusFilter(items) {
  const select = document.getElementById("installmentStatus");
  const selected = select.value;
  const order = ["unpaid", "partial", "overdue", "paid"];
  const counts = Object.fromEntries(order.map(status => [status, items.filter(item => item.status === status).length]));
  select.innerHTML = `<option value="">همهٔ وضعیت‌ها</option>${order.filter(status => counts[status]).map(status => `<option value="${status}">${statusLabel[status]} (${persianDigits(counts[status])})</option>`).join("")}`;
  select.value = counts[selected] ? selected : "";
}

function renderInstallmentRows() {
  const selectedStatus = document.getElementById("installmentStatus").value;
  currentInstallments = selectedStatus ? baseInstallments.filter(item => item.status === selectedStatus) : baseInstallments;
  renderRows("installmentRows", currentInstallments.map(item => {
    const paymentButton = item.remaining_amount > 0 ? `<button class="quiet pay-installment" data-id="${item.id}">پرداخت</button>` : "";
    return `<tr><td>${escapeHtml(item.title)}</td><td>${item.due_date}</td><td>${currency(item.amount)}</td><td>${currency(item.paid_amount)}</td><td>${currency(item.remaining_amount)}</td><td><span class="badge ${item.status}">${statusLabel[item.status]}</span></td><td class="row-actions"><button class="quiet edit-commitment" data-id="${item.id}">ویرایش تعهد</button><button class="quiet edit-installment" data-id="${item.id}">ویرایش قسط</button>${paymentButton}<button class="quiet payment-details" data-id="${item.id}">ریز پرداخت‌ها</button></td></tr>`;
  }), 7);
}
async function loadInstallments() {
  const query = installmentQuery(); baseInstallments = await api(`/installments${query ? `?${query}` : ""}`);
  updateStatusFilter(baseInstallments); renderInstallmentRows();
}

function openInlinePayment(installmentId) {
  const item = currentInstallments.find(row => row.id === installmentId); if (!item) return;
  document.querySelectorAll(".inline-payment-row").forEach(row => row.remove());
  const target = document.querySelector(`.pay-installment[data-id="${installmentId}"]`)?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-payment-row"><td colspan="7"><form class="inline-payment-form" data-id="${item.id}"><b>ثبت پرداخت: ${escapeHtml(item.title)} — ${item.due_date}</b><div class="inline-payment-fields"><div class="field"><label>مبلغ پرداخت</label><input name="amount" data-amount inputmode="numeric" value="${item.remaining_amount.toLocaleString("fa-IR")}" required /></div><div class="field"><label>تاریخ پرداخت شمسی</label><input name="paid_on" inputmode="numeric" value="${todayJalali()}" required /></div><div class="field"><label>حساب</label><select name="account_id">${accountOptions()}</select></div><div class="field"><label>یادداشت</label><input name="note" maxlength="300" placeholder="اختیاری" /></div><button class="primary" type="submit">ثبت پرداخت</button><button class="quiet cancel-inline-payment" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
}
async function openPaymentDetails(installmentId, trigger) {
  document.querySelectorAll(".payment-details-row").forEach(row => row.remove());
  const row = trigger.closest("tr");
  const details = await api(`/installments/${installmentId}/details`);
  const payments = details.payments.map(payment => `<form class="payment-edit-form inline-edit-fields" data-id="${payment.id}"><span>پرداخت #${persianDigits(payment.id)}</span><input name="amount" aria-label="مبلغ پرداخت" data-amount inputmode="numeric" value="${Number(payment.amount).toLocaleString("fa-IR")}" required /><input name="paid_on" aria-label="تاریخ پرداخت شمسی" value="${escapeHtml(payment.paid_on)}" required /><select name="account_id" aria-label="حساب"><option value="">بدون حساب</option>${accounts.map(account => `<option value="${account.id}" ${account.id === payment.account_id ? "selected" : ""}>${escapeHtml(account.name)}</option>`).join("")}</select><input name="note" aria-label="یادداشت" maxlength="300" value="${escapeHtml(payment.note || "")}" /><button class="quiet" type="submit">ذخیره پرداخت</button><button class="quiet delete-payment" type="button" data-id="${payment.id}">حذف پرداخت</button></form>`).join("") || "پرداختی ثبت نشده است.";
  const history = details.history.map(log => `<li>${escapeHtml(log.created_at)} · ${escapeHtml({ create: "ثبت", update: "ویرایش", delete: "حذف" }[log.action] || log.action)} ${escapeHtml({ commitment: "تعهد", installment: "قسط", payment: "پرداخت" }[log.resource_type] || log.resource_type)} · ${escapeHtml(auditText(log.details))}</li>`).join("") || "<li>تغییری ثبت نشده است.</li>";
  row.insertAdjacentHTML("afterend", `<tr class="payment-details-row"><td colspan="7"><b>ریز پرداخت‌ها</b>${payments}<details><summary>تاریخچه تغییرات</summary><ul>${history}</ul></details><p class="form-message" role="status"></p><button class="quiet close-payment-details" type="button">بستن</button></td></tr>`);
}
function openInlineCommitmentEdit(installmentId) {
  const item = currentInstallments.find(row => row.id === installmentId); if (!item) return;
  const target = document.querySelector(`.edit-commitment[data-id="${installmentId}"]`)?.closest("tr"); if (!target) return;
  openGroupedCommitmentEdit(item, target, false);
}
function openGroupedCommitmentEdit(item, target, grid) {
  document.querySelectorAll(grid ? ".inline-grid-edit-row" : ".inline-edit-row").forEach(row => row.remove());
  const kind = commitmentList.find(row => row.id === (item.commitment_id || item.id))?.kind || item.kind;
  target.insertAdjacentHTML("afterend", `<tr class="${grid ? "inline-grid-edit-row" : "inline-edit-row"}"><td colspan="${grid ? 9 : 7}"><form class="inline-group-commitment-form" data-id="${item.commitment_id || item.id}"><b>ویرایش تعهد و همهٔ ریزتعهدهای هم‌عنوان</b><div class="inline-edit-fields"><div class="field"><label>عنوان</label><input name="title" value="${escapeHtml(item.title)}" required /></div><div class="field"><label>نوع</label><input name="kind" value="${escapeHtml(kind)}" required /></div><button class="primary" type="submit">ذخیرهٔ همه</button><button class="quiet ${grid ? "cancel-grid-edit" : "cancel-inline-edit"}" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
}
function openInlineInstallmentEdit(installmentId) {
  const item = currentInstallments.find(row => row.id === installmentId); if (!item) return;
  document.querySelectorAll(".inline-edit-row").forEach(row => row.remove());
  const target = document.querySelector(`.edit-installment[data-id="${installmentId}"]`)?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-edit-row"><td colspan="7"><form class="inline-installment-form" data-id="${item.id}"><b>ویرایش جزئی قسط</b><div class="inline-edit-fields"><div class="field"><label>سررسید شمسی</label><input name="due_date" inputmode="numeric" value="${item.due_date}" required /></div><div class="field"><label>مبلغ قسط</label><input name="amount" data-amount inputmode="numeric" value="${Number(item.amount).toLocaleString("fa-IR")}" required /></div><div class="field"><label>یادداشت</label><input name="note" maxlength="300" value="${escapeHtml(item.note || "")}" /></div><button class="primary" type="submit">ذخیرهٔ قسط</button><button class="quiet cancel-inline-edit" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
}
function openGridCommitmentEdit(commitmentId, trigger = null) {
  const item = commitmentList.find(row => row.id === commitmentId); if (!item) return;
  document.querySelectorAll(".inline-grid-edit-row").forEach(row => row.remove());
  const target = (trigger || document.querySelector(`.edit-grid-group[data-id="${commitmentId}"]`))?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-grid-edit-row"><td colspan="7"><form class="inline-commitment-form" data-id="${item.id}"><b>ویرایش کلی تعهد: ${escapeHtml(item.title)}</b><div class="inline-edit-fields"><div class="field"><label>عنوان</label><input name="title" value="${escapeHtml(item.title)}" required /></div><div class="field"><label>نوع</label><input name="kind" value="${escapeHtml(item.kind)}" required /></div><div class="field"><label>مبلغ کل</label><input name="total_amount" data-amount inputmode="numeric" value="${item.total_amount ? Number(item.total_amount).toLocaleString("fa-IR") : ""}" /></div><button class="primary" type="submit">ذخیرهٔ تعهد</button><button class="quiet cancel-grid-edit" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
  target.nextElementSibling.firstElementChild.colSpan = 9;
}
function openGroupedCommitmentDetails(title, trigger) {
  const group = groupedCommitments().find(item => item.title === title);
  if (!group) return;
  document.querySelectorAll(".inline-grid-edit-row").forEach(row => row.remove());
  const target = trigger.closest("tr");
  const rows = group.members.map(item => `<tr><td>${item.total_amount == null ? "—" : currency(item.total_amount)}</td><td>${escapeHtml(item.kind)}</td><td>${persianDigits(item.installment_count)}</td><td>${currency(item.planned_amount)}</td><td>${currency(item.paid_amount)}</td><td><button type="button" class="quiet edit-group-member" data-id="${item.id}">ویرایش این تعهد</button></td></tr>`).join("");
  target.insertAdjacentHTML("afterend", `<tr class="inline-grid-edit-row"><td colspan="9"><b>تعهدات ثبت‌شده با عنوان «${escapeHtml(group.title)}»</b><div class="table-wrap"><table><thead><tr><th>مبلغ کل</th><th>نوع</th><th>تعداد اقساط</th><th>جمع اقساط</th><th>پرداخت‌شده</th><th>عملیات</th></tr></thead><tbody>${rows}</tbody></table></div><button type="button" class="quiet cancel-grid-edit">بستن</button></td></tr>`);
}
function commitmentPayload() { return { title: document.getElementById("commitmentTitle").value, kind: document.getElementById("commitmentKind").value, total_amount: amountNumber(document.getElementById("commitmentTotal").value) || null, installment_amount: amountNumber(document.getElementById("installmentAmount").value), installment_count: Number(document.getElementById("installmentCount").value), first_due_date: document.getElementById("firstDueDate").value, interval_months: Number(document.getElementById("intervalMonths").value) }; }
async function previewCommitment() {
  setMessage("commitmentMessage", "");
  try {
    commitmentPreview = await api("/commitments/preview", { method: "POST", body: JSON.stringify(commitmentPayload()) });
    document.getElementById("previewSummary").textContent = `${persianDigits(commitmentPreview.installments.length)} قسط · از ${commitmentPreview.first_due_date} تا ${commitmentPreview.last_due_date} · جمع ${currency(commitmentPreview.planned_total)}`;
    document.getElementById("lastDueDate").value = commitmentPreview.last_due_date;
    renderRows("previewRows", commitmentPreview.installments.map(item => `<tr><td>${persianDigits(item.number)}</td><td>${item.due_date}</td><td>${currency(item.amount)}</td></tr>`), 3);
    document.getElementById("saveCommitment").disabled = false;
  } catch (error) { commitmentPreview = null; document.getElementById("saveCommitment").disabled = true; setMessage("commitmentMessage", error.message, true); }
}
async function refreshAll() { await Promise.all([loadDashboard(), loadTransactions(), loadInstallments()]); }
async function loadReleases() { const items = await api("/releases"); document.getElementById("releaseList").innerHTML = items.length ? items.map(item => `<article class="release-item"><h2>نگارش ${escapeHtml(item.version)} — ${escapeHtml(item.title)}</h2><p class="release-meta">${escapeHtml(item.released_at)} · بخش‌های تحت تأثیر: ${escapeHtml(item.affected_areas)}</p><p>${escapeHtml(item.description)}</p></article>`).join("") : "<p>تاریخچه‌ای ثبت نشده است.</p>"; }
async function loadSettings() { const settings = await api("/settings"); document.getElementById("backupEnabled").checked = settings.backup_enabled; document.getElementById("backupDirectory").value = settings.backup_directory; }

document.querySelectorAll(".nav-link,[data-page]").forEach(button => button.addEventListener("click", () => { const page = button.dataset.page; if (!page) return; document.querySelectorAll(".page").forEach(section => section.classList.toggle("active", section.id === page)); document.querySelectorAll(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.page === page)); if (page === "commitments") loadInstallments(); if (page === "settings") loadSettings(); }));
document.getElementById("transactionType").addEventListener("change", updateCategories);
document.getElementById("dashboardMonth").addEventListener("change", loadDashboard);
document.getElementById("transactionMonth").addEventListener("change", loadTransactions);
["installmentMonth", "installmentCommitment"].forEach(id => document.getElementById(id).addEventListener("change", loadInstallments));
document.getElementById("installmentStatus").addEventListener("change", renderInstallmentRows);
document.getElementById("installmentSearch").addEventListener("input", () => { clearTimeout(window.installmentSearchTimer); window.installmentSearchTimer = setTimeout(loadInstallments, 250); });
document.getElementById("clearInstallmentFilters").addEventListener("click", () => { ["installmentStatus", "installmentCommitment", "installmentSearch"].forEach(id => document.getElementById(id).value = ""); const now = currentJalaliParts(); document.getElementById("installmentMonth").value = jalaliMonthKey(now.year, now.month); loadInstallments(); });
document.getElementById("previewCommitment").addEventListener("click", previewCommitment);
document.querySelectorAll("#commitmentForm input, #commitmentForm select").forEach(input => ["input", "change"].forEach(eventName => input.addEventListener(eventName, () => { if (input.id === "lastDueDate") return; commitmentPreview = null; document.getElementById("saveCommitment").disabled = true; document.getElementById("lastDueDate").value = ""; })));

document.getElementById("transactionForm").addEventListener("submit", async event => { event.preventDefault(); setMessage("transactionMessage", ""); try { await api("/transactions", { method: "POST", body: JSON.stringify({ transaction_type: document.getElementById("transactionType").value, amount: amountNumber(document.getElementById("transactionAmount").value), occurred_on: document.getElementById("transactionDate").value, category_id: Number(document.getElementById("transactionCategory").value), account_id: Number(document.getElementById("transactionAccount").value) || null, note: document.getElementById("transactionNote").value }) }); event.target.reset(); setJalaliDateDefaults(); updateCategories(); setMessage("transactionMessage", "تراکنش ثبت شد."); await refreshAll(); } catch (error) { setMessage("transactionMessage", error.message, true); } });
document.getElementById("commitmentForm").addEventListener("submit", async event => { event.preventDefault(); if (!commitmentPreview) return previewCommitment(); setMessage("commitmentMessage", ""); try { await api("/commitments", { method: "POST", body: JSON.stringify(commitmentPayload()) }); event.target.reset(); setJalaliDateDefaults(); document.getElementById("installmentCount").value = 12; document.getElementById("intervalMonths").value = 1; commitmentPreview = null; document.getElementById("saveCommitment").disabled = true; document.getElementById("previewRows").innerHTML = `<tr><td colspan="3" class="empty-cell">پیش‌نمایشی ایجاد نشده است.</td></tr>`; document.getElementById("previewSummary").textContent = "تعهد ثبت شد."; setMessage("commitmentMessage", "تعهد و همهٔ اقساط آن ثبت شد."); await loadReferenceData(); await refreshAll(); } catch (error) { setMessage("commitmentMessage", error.message, true); } });
document.getElementById("installmentRows").addEventListener("click", async event => { const payment = event.target.closest(".pay-installment"), commitment = event.target.closest(".edit-commitment"), installment = event.target.closest(".edit-installment"), details = event.target.closest(".payment-details"), deletion = event.target.closest(".delete-payment"); if (payment) openInlinePayment(Number(payment.dataset.id)); if (commitment) openInlineCommitmentEdit(Number(commitment.dataset.id)); if (installment) openInlineInstallmentEdit(Number(installment.dataset.id)); if (details) { try { await openPaymentDetails(Number(details.dataset.id), details); } catch (error) { alert(error.message); } } if (deletion && confirm("این پرداخت حذف شود؟")) { try { await api(`/payments/${deletion.dataset.id}`, { method: "DELETE" }); await loadReferenceData(); await refreshAll(); } catch (error) { deletion.closest("tr").querySelector(".form-message").textContent = error.message; } } if (event.target.closest(".cancel-inline-payment, .cancel-inline-edit, .close-payment-details")) event.target.closest("tr").remove(); });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".payment-edit-form"); if (!form) return; event.preventDefault(); const data = new FormData(form); try { await api(`/payments/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify({ amount: amountNumber(data.get("amount")), paid_on: data.get("paid_on"), account_id: Number(data.get("account_id")) || null, note: data.get("note") }) }); await loadReferenceData(); await refreshAll(); } catch (error) { form.closest("tr").querySelector(".form-message").textContent = error.message; } });
document.getElementById("commitmentRows").addEventListener("click", event => { const edit = event.target.closest(".edit-grid-group"), details = event.target.closest(".view-group-details"), member = event.target.closest(".edit-group-member"); if (edit) { const item = commitmentList.find(row => row.id === Number(edit.dataset.id)); if (item) openGroupedCommitmentEdit(item, edit.closest("tr"), true); } if (details) openGroupedCommitmentDetails(details.dataset.title, details); if (member) { const anchor = member.closest(".inline-grid-edit-row").previousElementSibling.querySelector(".edit-grid-group"); member.closest(".inline-grid-edit-row").remove(); openGridCommitmentEdit(Number(member.dataset.id), anchor); } if (event.target.closest(".cancel-grid-edit")) event.target.closest("tr").remove(); });
for (const id of ["installmentRows", "commitmentRows"]) document.getElementById(id).addEventListener("submit", async event => {
  const form = event.target.closest(".inline-group-commitment-form"); if (!form) return;
  event.preventDefault();
  const message = form.querySelector(".form-message"); message.textContent = "";
  const data = new FormData(form);
  try {
    await api(`/commitments/${form.dataset.id}/group`, { method: "PATCH", body: JSON.stringify({ title: data.get("title"), kind: data.get("kind") }) });
    await loadReferenceData(); await refreshAll();
  } catch (error) { message.textContent = error.message; message.classList.add("error"); }
});
document.getElementById("commitmentGridFilters").addEventListener("change", event => {
  const input = event.target.closest('input[type="checkbox"]');
  if (!input) return;
  const facet = input.closest("[data-filter]");
  const filter = facet.dataset.filter;
  if (input.value === "") commitmentGridFilters[filter].clear();
  else if (input.checked) commitmentGridFilters[filter].add(input.value);
  else commitmentGridFilters[filter].delete(input.value);
  renderCommitmentGrid();
  facet.open = false;
});
document.addEventListener("click", event => {
  const currentFacet = event.target.closest("#commitmentGridFilters .facet");
  document.querySelectorAll("#commitmentGridFilters .facet[open]").forEach(facet => {
    if (facet !== currentFacet) facet.open = false;
  });
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") document.querySelectorAll("#commitmentGridFilters .facet[open]").forEach(facet => { facet.open = false; });
});
document.getElementById("resetCommitmentFilters").addEventListener("click", () => {
  Object.values(commitmentGridFilters).forEach(values => values.clear());
  renderCommitmentGrid();
});
document.querySelectorAll(".commitment-grid-panel th[data-sort]").forEach(th => {
  const sort = () => { commitmentSort = { key: th.dataset.sort, direction: commitmentSort.key === th.dataset.sort && commitmentSort.direction === "asc" ? "desc" : "asc" }; renderCommitmentGrid(); };
  th.addEventListener("click", sort);
  th.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); sort(); } });
});
document.addEventListener("change", event => { if (event.target.matches("[data-amount]")) formatAmountInput(event.target); });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-payment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); try { await api("/payments", { method: "POST", body: JSON.stringify({ installment_id: Number(form.dataset.id), amount: amountNumber(data.get("amount")), paid_on: data.get("paid_on"), account_id: Number(data.get("account_id")) || null, note: data.get("note") }) }); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-commitment-form, .inline-installment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); const isCommitment = form.classList.contains("inline-commitment-form"); const payload = isCommitment ? { title: data.get("title"), kind: data.get("kind"), total_amount: amountNumber(data.get("total_amount")) || null } : { due_date: data.get("due_date"), amount: amountNumber(data.get("amount")), note: data.get("note") }; try { await api(`/${isCommitment ? "commitments" : "installments"}/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify(payload) }); await loadReferenceData(); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("commitmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-commitment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); try { await api(`/commitments/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify({ title: data.get("title"), kind: data.get("kind"), total_amount: amountNumber(data.get("total_amount")) || null }) }); await loadReferenceData(); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("settingsForm").addEventListener("submit", async event => { event.preventDefault(); setMessage("settingsMessage", ""); try { await api("/settings", { method: "PUT", body: JSON.stringify({ backup_enabled: document.getElementById("backupEnabled").checked, backup_directory: document.getElementById("backupDirectory").value }) }); setMessage("settingsMessage", "تنظیمات پشتیبان‌گیری ذخیره شد."); } catch (error) { setMessage("settingsMessage", error.message, true); } });
document.getElementById("manualBackup").addEventListener("click", async () => { setMessage("settingsMessage", ""); try { const result = await api("/backups", { method: "POST" }); setMessage("settingsMessage", `پشتیبان ایجاد شد: ${result.path}`); } catch (error) { setMessage("settingsMessage", error.message, true); } });

populateMonthSelectors(); setJalaliDateDefaults(); loadReferenceData().then(async () => { await refreshAll(); await loadReleases(); }).catch(error => document.body.insertAdjacentHTML("afterbegin", `<p class="fatal" role="alert">${escapeHtml(error.message)}</p>`));
