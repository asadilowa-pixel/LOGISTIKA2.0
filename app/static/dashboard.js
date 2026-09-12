function toIsoDate(date) {
    return date.toISOString().slice(0, 10);
}

function setDefaultDateRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 30);
    document.getElementById("date-from").value = toIsoDate(from);
    document.getElementById("date-to").value = toIsoDate(to);
}

function buildQuery(params) {
    const usp = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined && value !== "") {
            usp.set(key, value);
        }
    }
    return usp.toString();
}

function currentPeriodAndClient() {
    return {
        date_from: document.getElementById("date-from").value,
        date_to: document.getElementById("date-to").value,
        id_client: document.getElementById("id-client").value,
    };
}

async function fetchStocks() {
    const marketplace = document.getElementById("stocks-marketplace").value;
    const idClient = document.getElementById("id-client").value;
    const query = buildQuery({ marketplace, id_client: idClient });
    const resp = await fetch(`/stocks/unified?${query}`);
    const rows = await resp.json();

    const body = document.getElementById("stocks-body");
    body.innerHTML = "";
    for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${row.marketplace}</td>
            <td>${row.fulfillment}</td>
            <td>${row.article_seller}</td>
            <td>${row.warehouse}</td>
            <td>${row.quantity}</td>
            <td>${row.cabinet}</td>
        `;
        body.appendChild(tr);
    }
}

const EXPENSE_FIELD_LABELS = {
    logistics_cost: "Логистика",
    returned_logistics_cost: "Возвраты логистики",
    last_mile_cost: "Последняя миля",
    cancel_last_mile_cost: "Отмена последней мили",
    reverse_logistics_cost: "Обратная логистика",
};

function renderExpensesCard(elementId, data) {
    const el = document.getElementById(elementId);
    if (data === null || data === undefined) {
        el.textContent = "нет данных";
        return;
    }
    let html = "";
    for (const [key, value] of Object.entries(data)) {
        if (key === "total") continue;
        const label = EXPENSE_FIELD_LABELS[key] || key;
        html += `<div>${label}: ${value.toFixed(2)}</div>`;
    }
    html += `<div><strong>Итого: ${data.total.toFixed(2)}</strong></div>`;
    el.innerHTML = html;
}

async function fetchExpenses() {
    const query = buildQuery(currentPeriodAndClient());
    const resp = await fetch(`/expenses/logistics?${query}`);
    const data = await resp.json();
    renderExpensesCard("expenses-ozon", data.ozon);
    renderExpensesCard("expenses-wb", data.wb);
}

async function fetchFbsCounts() {
    const query = buildQuery(currentPeriodAndClient());
    const resp = await fetch(`/orders/fbs-count?${query}`);
    const data = await resp.json();
    document.getElementById("fbs-ozon").textContent = data.ozon;
    document.getElementById("fbs-wb").textContent = data.wb;
}

function refreshPeriodBlocks() {
    fetchExpenses();
    fetchFbsCounts();
}

function refreshAll() {
    fetchStocks();
    refreshPeriodBlocks();
}

function init() {
    setDefaultDateRange();
    document.getElementById("date-from").addEventListener("change", refreshPeriodBlocks);
    document.getElementById("date-to").addEventListener("change", refreshPeriodBlocks);
    document.getElementById("id-client").addEventListener("change", refreshAll);
    document.getElementById("stocks-marketplace").addEventListener("change", fetchStocks);
    refreshAll();
}

document.addEventListener("DOMContentLoaded", init);
