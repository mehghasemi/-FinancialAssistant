const api = (path, options = {}) => fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options }).then(async response => {
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "خطا در ارتباط با برنامه");
  return data;
});

const currency = value => `${Number(value || 0).toLocaleString("fa-IR")} تومان`;
const statusLabel = { paid: "پرداخت‌شده", partial: "پرداخت جزئی", overdue: "معوق", unpaid: "پرداخت‌نشده" };
const jalaliMonths = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
let accounts = [], categories = [], commitmentFilters = [], commitmentList = [], currentInstallments = [], baseInstallments = [], commitmentPreview = null;
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const persianDigits = value => String(value).replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[digit]);
const latinDigits = value => String(value).replace(/[۰-۹]/g, digit => "۰۱۲۳۴۵۶۷۸۹".indexOf(digit)).replace(/[٠-٩]/g, digit => "٠١٢٣٤٥٦٧٨٩".indexOf(digit));
const amountNumber = value => Number(latinDigits(value).replace(/[٬,\s]/g, "")) || 0;

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
function renderCommitmentGrid() {
  renderRows("commitmentRows", commitmentList.map(item => `<tr><td>${escapeHtml(item.title)}</td><td>${escapeHtml(item.kind)}</td><td>${item.total_amount ? currency(item.total_amount) : "—"}</td><td>${persianDigits(item.installment_count)}</td><td>${currency(item.planned_amount)}</td><td>${currency(item.paid_amount)}</td><td><button class="quiet edit-grid-commitment" data-id="${item.id}">ویرایش</button></td></tr>`), 7);
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
    return `<tr><td>${escapeHtml(item.title)}</td><td>${item.due_date}</td><td>${currency(item.amount)}</td><td>${currency(item.paid_amount)}</td><td>${currency(item.remaining_amount)}</td><td><span class="badge ${item.status}">${statusLabel[item.status]}</span></td><td class="row-actions"><button class="quiet edit-commitment" data-id="${item.id}">ویرایش تعهد</button><button class="quiet edit-installment" data-id="${item.id}">ویرایش قسط</button>${paymentButton}</td></tr>`;
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
function openInlineCommitmentEdit(installmentId) {
  const item = currentInstallments.find(row => row.id === installmentId); if (!item) return;
  document.querySelectorAll(".inline-edit-row").forEach(row => row.remove());
  const target = document.querySelector(`.edit-commitment[data-id="${installmentId}"]`)?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-edit-row"><td colspan="7"><form class="inline-commitment-form" data-id="${item.commitment_id}"><b>ویرایش کلی تعهد</b><div class="inline-edit-fields"><div class="field"><label>عنوان</label><input name="title" value="${escapeHtml(item.title)}" required /></div><div class="field"><label>نوع</label><input name="kind" value="${escapeHtml(item.kind)}" required /></div><div class="field"><label>مبلغ کل</label><input name="total_amount" data-amount inputmode="numeric" value="${item.total_amount ? Number(item.total_amount).toLocaleString("fa-IR") : ""}" /></div><button class="primary" type="submit">ذخیرهٔ تعهد</button><button class="quiet cancel-inline-edit" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
}
function openInlineInstallmentEdit(installmentId) {
  const item = currentInstallments.find(row => row.id === installmentId); if (!item) return;
  document.querySelectorAll(".inline-edit-row").forEach(row => row.remove());
  const target = document.querySelector(`.edit-installment[data-id="${installmentId}"]`)?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-edit-row"><td colspan="7"><form class="inline-installment-form" data-id="${item.id}"><b>ویرایش جزئی قسط</b><div class="inline-edit-fields"><div class="field"><label>سررسید شمسی</label><input name="due_date" inputmode="numeric" value="${item.due_date}" required /></div><div class="field"><label>مبلغ قسط</label><input name="amount" data-amount inputmode="numeric" value="${Number(item.amount).toLocaleString("fa-IR")}" required /></div><div class="field"><label>یادداشت</label><input name="note" maxlength="300" value="${escapeHtml(item.note || "")}" /></div><button class="primary" type="submit">ذخیرهٔ قسط</button><button class="quiet cancel-inline-edit" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
}
function openGridCommitmentEdit(commitmentId) {
  const item = commitmentList.find(row => row.id === commitmentId); if (!item) return;
  document.querySelectorAll(".inline-grid-edit-row").forEach(row => row.remove());
  const target = document.querySelector(`.edit-grid-commitment[data-id="${commitmentId}"]`)?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-grid-edit-row"><td colspan="7"><form class="inline-commitment-form" data-id="${item.id}"><b>ویرایش کلی تعهد: ${escapeHtml(item.title)}</b><div class="inline-edit-fields"><div class="field"><label>عنوان</label><input name="title" value="${escapeHtml(item.title)}" required /></div><div class="field"><label>نوع</label><input name="kind" value="${escapeHtml(item.kind)}" required /></div><div class="field"><label>مبلغ کل</label><input name="total_amount" data-amount inputmode="numeric" value="${item.total_amount ? Number(item.total_amount).toLocaleString("fa-IR") : ""}" /></div><button class="primary" type="submit">ذخیرهٔ تعهد</button><button class="quiet cancel-grid-edit" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
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
document.getElementById("installmentRows").addEventListener("click", event => { const payment = event.target.closest(".pay-installment"), commitment = event.target.closest(".edit-commitment"), installment = event.target.closest(".edit-installment"); if (payment) openInlinePayment(Number(payment.dataset.id)); if (commitment) openInlineCommitmentEdit(Number(commitment.dataset.id)); if (installment) openInlineInstallmentEdit(Number(installment.dataset.id)); if (event.target.closest(".cancel-inline-payment") || event.target.closest(".cancel-inline-edit")) event.target.closest("tr").remove(); });
document.getElementById("commitmentRows").addEventListener("click", event => { const edit = event.target.closest(".edit-grid-commitment"); if (edit) openGridCommitmentEdit(Number(edit.dataset.id)); if (event.target.closest(".cancel-grid-edit")) event.target.closest("tr").remove(); });
document.addEventListener("change", event => { if (event.target.matches("[data-amount]")) formatAmountInput(event.target); });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-payment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); try { await api("/payments", { method: "POST", body: JSON.stringify({ installment_id: Number(form.dataset.id), amount: amountNumber(data.get("amount")), paid_on: data.get("paid_on"), account_id: Number(data.get("account_id")) || null, note: data.get("note") }) }); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-commitment-form, .inline-installment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); const isCommitment = form.classList.contains("inline-commitment-form"); const payload = isCommitment ? { title: data.get("title"), kind: data.get("kind"), total_amount: amountNumber(data.get("total_amount")) || null } : { due_date: data.get("due_date"), amount: amountNumber(data.get("amount")), note: data.get("note") }; try { await api(`/${isCommitment ? "commitments" : "installments"}/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify(payload) }); await loadReferenceData(); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("commitmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-commitment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); try { await api(`/commitments/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify({ title: data.get("title"), kind: data.get("kind"), total_amount: amountNumber(data.get("total_amount")) || null }) }); await loadReferenceData(); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("settingsForm").addEventListener("submit", async event => { event.preventDefault(); setMessage("settingsMessage", ""); try { await api("/settings", { method: "PUT", body: JSON.stringify({ backup_enabled: document.getElementById("backupEnabled").checked, backup_directory: document.getElementById("backupDirectory").value }) }); setMessage("settingsMessage", "تنظیمات پشتیبان‌گیری ذخیره شد."); } catch (error) { setMessage("settingsMessage", error.message, true); } });
document.getElementById("manualBackup").addEventListener("click", async () => { setMessage("settingsMessage", ""); try { const result = await api("/backups", { method: "POST" }); setMessage("settingsMessage", `پشتیبان ایجاد شد: ${result.path}`); } catch (error) { setMessage("settingsMessage", error.message, true); } });

populateMonthSelectors(); setJalaliDateDefaults(); loadReferenceData().then(async () => { await refreshAll(); await loadReleases(); }).catch(error => document.body.insertAdjacentHTML("afterbegin", `<p class="fatal" role="alert">${escapeHtml(error.message)}</p>`));
