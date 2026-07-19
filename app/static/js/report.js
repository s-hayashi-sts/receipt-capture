// static/js/report.js

// グローバルで現在の表示年月と選択日を管理（デフォルトは今日）
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1; // 1~12

// DB上の最古データの年月（⑥の判定に使用。date-range取得までは仮に現在月をセット）
let minYear = currentYear;
let minMonth = currentMonth;

const today = new Date();
const y = today.getFullYear();
const m = String(today.getMonth() + 1).padStart(2, '0');
const d = String(today.getDate()).padStart(2, '0');
let selectedDateStr = `${y}-${m}-${d}`;

document.addEventListener("DOMContentLoaded", async () => {
    await fetchDateRange();       // ⑥ 最古年月を先に取得
    await renderCalendar(currentYear, currentMonth);
    loadDailyDetail(selectedDateStr); // デフォルトで今日の詳細を表示

    document.getElementById("prev-month").addEventListener("click", () => {
        let y2 = currentYear, m2 = currentMonth - 1;
        if (m2 < 1) { m2 = 12; y2--; }
        goToMonth(y2, m2);
    });

    document.getElementById("next-month").addEventListener("click", () => {
        let y2 = currentYear, m2 = currentMonth + 1;
        if (m2 > 12) { m2 = 1; y2++; }
        goToMonth(y2, m2);
    });
});

// DBに登録された最古のレシート年月を取得（⑥用）
async function fetchDateRange() {
    try {
        const response = await fetch("/api/date-range");
        const data = await response.json();
        minYear = data.earliest_year;
        minMonth = data.earliest_month;
    } catch (e) {
        console.error("date-range取得に失敗:", e);
    }
}

// 「今月より未来か」「最古月より前か」を判定してボタンの有効/無効を切り替える（⑤⑥）
function updateNavButtons(year, month) {
    const now = new Date();
    const thisYear = now.getFullYear();
    const thisMonth = now.getMonth() + 1;

    const isFutureOrCurrent = (year > thisYear) || (year === thisYear && month >= thisMonth);
    document.getElementById("next-month").disabled = isFutureOrCurrent;

    const isEarliestOrBefore = (year < minYear) || (year === minYear && month <= minMonth);
    document.getElementById("prev-month").disabled = isEarliestOrBefore;
}

// 月移動時：⑨ その月の1日の内訳を表示する
function goToMonth(year, month) {
    // 範囲外への移動を念のため防止（ボタンdisabled済みだが二重ガード）
    const now = new Date();
    if (year > now.getFullYear() || (year === now.getFullYear() && month > now.getMonth() + 1)) return;
    if (year < minYear || (year === minYear && month < minMonth)) return;

    currentYear = year;
    currentMonth = month;
    selectedDateStr = `${year}-${String(month).padStart(2, '0')}-01`;

    renderCalendar(year, month);
    loadDailyDetail(selectedDateStr);
}

// カレンダーを描画する関数
async function renderCalendar(year, month) {
    document.getElementById("calendar-title").textContent = `${year}年${month}月`;
    updateNavButtons(year, month); // ⑤⑥ ボタン制御

    const cellsContainer = document.getElementById("calendar-cells");
    cellsContainer.innerHTML = "";

    const response = await fetch(`/api/monthly-summary?year=${year}&month=${month}`);
    const dailyTotals = await response.json();

    // ⑩ 月合計を計算して表示
    const monthlyTotal = Object.values(dailyTotals).reduce((sum, v) => sum + v, 0);
    document.getElementById("monthly-total").textContent = `¥${monthlyTotal.toLocaleString()}`;

    // 月の初日の曜日（0=日〜6=土）と、総日数を計算
    const firstDayIndex = new Date(year, month - 1, 1).getDay();
    const totalDays = new Date(year, month, 0).getDate();

    // 空白マスの挿入（前月分の余白）
    for (let i = 0; i < firstDayIndex; i++) {
        const emptyCell = document.createElement("div");
        emptyCell.style.visibility = "hidden";
        cellsContainer.appendChild(emptyCell);
    }

    // 日付マスの生成
    for (let day = 1; day <= totalDays; day++) {
        const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const total = dailyTotals[dateStr] || 0;

        const activeClass = (dateStr === selectedDateStr) ? 'border border-primary border-3 fw-bold' : '';
        const priceDisplay = total > 0
            ? `<span class="badge bg-primary text-white" style="font-size: 0.65rem;">¥${total.toLocaleString()}</span>`
            : '<span class="badge" style="font-size: 0.65rem; visibility: hidden;">¥0</span>';

        const cell = document.createElement("div");
        cell.className = `text-center p-2 calendar-day-cell ${activeClass}`;
        cell.style.cursor = "pointer";
        cell.dataset.date = dateStr;

        cell.innerHTML = `
            <div>${day}</div>
            ${priceDisplay}
        `;

        cell.addEventListener("click", () => {
            onDateSelect(dateStr);
        });
        cellsContainer.appendChild(cell);
    }
}

// 日付がクリックされた時の処理（⑧）
function onDateSelect(dateStr) {
    selectedDateStr = dateStr;
    renderCalendar(currentYear, currentMonth);
    loadDailyDetail(dateStr);
}

// 内訳データを取得して画面下部に反映する関数
async function loadDailyDetail(dateStr) {
    const response = await fetch(`/api/daily-detail?date=${dateStr}`);
    const data = await response.json();

    const displayDate = dateStr.replace(/-/g, '/');
    document.getElementById("selected-date").textContent = displayDate;
    document.getElementById("selected-total").textContent = `¥${data.total_price.toLocaleString()}`;

    const listContainer = document.getElementById("expense-list");
    listContainer.innerHTML = "";

    if (data.items.length === 0) {
        listContainer.innerHTML = `<li class="list-group-item text-muted text-center">この日の出費はありません</li>`;
        return;
    }
    data.items.forEach(item => {
        const li = document.createElement("li");
        li.className = "list-group-item d-flex justify-content-between align-items-center px-0";
        li.innerHTML = `
            <span>・ ${item.item}</span>
            <span class="fw-bold">¥${item.price.toLocaleString()}</span>
        `;
        listContainer.appendChild(li);
    });
}