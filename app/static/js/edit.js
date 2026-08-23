// ページロード時の初期設定
document.addEventListener("DOMContentLoaded", () => {

    // metaタグからCSRFトークンを取得し、フォームのhidden inputに同じ値をセット
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    const csrfInput = document.getElementById("csrf_token_input");
    if (csrfInput) {
        csrfInput.value = csrfToken;
    }

    // datetime-local の初期値をセット (YYYY-MM-DD HH:mm -> YYYY-MM-DDTHH:mm)
    const dtInput = document.getElementById("registerDatetime");
    if (dtInput) {
        const now = new Date();
        const year = now.getFullYear(); // 現在の年を取得

        // 入力できる日付の最小値（現在の時刻から1年前）を計算
        const oneYearAgo = new Date();
        oneYearAgo.setFullYear(now.getFullYear() - 1); // 1年前の年に設定

        const minYear = oneYearAgo.getFullYear();
        const minMonth = String(oneYearAgo.getMonth() + 1).padStart(2, '0');
        const minDate = String(oneYearAgo.getDate()).padStart(2, '0');

        // YYYY-MM-DDTHH:mm 形式でセット
        const minDateTime = `${minYear}-${minMonth}-${minDate}T00:00`;

        // 最大値（現在時刻）を YYYY-MM-DDTHH:mm 形式で作る
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const date = String(now.getDate()).padStart(2, '0');
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const maxDateTime = `${year}-${month}-${date}T${hours}:${minutes}`;

        // input要素に制限をセット
        dtInput.min = minDateTime;
        dtInput.max = maxDateTime;

        const rawVal = dtInput.dataset.rawValue; //例 "2026-04-24 18:52"
        if (rawVal) {
            dtInput.value = rawVal.replace(" ", "T");
        }
    }
});

// 重複コードを削減するための共通 fetch 送信関数（ CSRFトークン付き）
function sendPostRequest(payload) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    fetch("/edit/update", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken // バックエンド（Flask-WTF / CSRFProtect）が要求するヘッダー名
        },
        credentials: "include",
        body: JSON.stringify(payload)
    })
    .then(res => {
        if (!res.ok) throw new Error("Network response was not ok");
        return res.json();
    })
    .then(data => {
        // 返却されたテーブル内のHTMLデータを差し替え
        document.getElementById("editForm").innerHTML = data.html;
    })
    .catch(err => {
        console.error("Error updating form:", err);
        alert("通信エラーが発生しました。ネットワーク接続を確認するか、ページを更新してください。");
    });
}    

// 税率の計算方法を取得
function getTaxCalcMode() {
    const checked = document.querySelector('input[name="tax_calc_mode"]:checked');
    return checked ? checked.value : "all";
}


// 日時情報の同期
function updateDatetime(input) {
    const errorDiv = document.getElementById("datetimeError");
    const errorText = document.getElementById("datetimeErrorText");

    // 1. 入力が空、またはブラウザの標準チェックで不正な形式の場合
    if (!input.value || !input.checkValidity()) {
        
        // 1年以上前（min未満）の場合
        if (input.validity.rangeUnderflow) {
            errorText.textContent = "1年以上前の日付は選択できません";
        } 
        // 現在時刻より未来（max超え）の場合
        else if (input.validity.rangeOverflow) {
            errorText.textContent = "未来の日時は入力できません。現在までの日時を入力してください。";
        } 
        // その他の入力不備（不完全な入力など）
        else {
            errorText.textContent = "正しい日時を入力してください。";
        }

        // エラーメッセージを表示して、赤枠をつける
        errorDiv.classList.remove("d-none");
        input.classList.add("is-invalid");
        return; // 不正なのでサーバーへの送信（fetch）は中止する
    }

    // 2. チェックを通過した場合（正常系）
    errorDiv.classList.add("d-none");     // エラーメッセージを隠す
    input.classList.remove("is-invalid"); // 赤枠を消して正常に戻す
    input.classList.add("is-valid");      // （任意）緑の成功枠をつける

    // 送信時は T を半角スペースに戻して Flask 側の strftime 形式に合わせる
    const formattedDatetime = input.value.replace("T", " ");

    sendPostRequest({
        action: "update_datetime",
        datetime: formattedDatetime,
        tax_calc_mode: getTaxCalcMode()
    });
}

// ラジオボタンで税率の計算方法を切り替える
function changeTaxMode() {
    tax_calc_mode = document.querySelector('input[name="tax_calc_mode"]:checked').value;
    sendPostRequest({
        action: "change_calc_mode",
        tax_calc_mode: getTaxCalcMode()
    });
}

// 入力要素が現在の DOM 上に正しく存在しているか検証するヘルパー関数
function isValidElement(element) {
    if (!element) return false;
    // document.body 内に含まれているか（＝すでに破棄された古い DOM でないか）を判定
    return document.body.contains(element);
}

// 品目入力時
function updateName(input) {
    // 送信前に要素が最新の DOM に存在するかチェック
    if (!isValidElement(input)) return;

    sendPostRequest({
        action: "update_name",
        index: parseInt(input.dataset.index),
        name: input.value, 
        tax_calc_mode: getTaxCalcMode()
    });
}

// 金額入力時
function updatePrice(input) {
    // 送信前に要素が最新の DOM に存在するかチェック
    if (!isValidElement(input)) return;

    sendPostRequest({
        action: "update_price",
        index: parseInt(input.dataset.index),
        price: parseInt(input.value) || 0, 
        tax_calc_mode: getTaxCalcMode()
    });
}

// 税率の変更
function updateTax(selectElement) {
    // 送信前に要素が最新の DOM に存在するかチェック
    if (!isValidElement(selectElement)) return;

    sendPostRequest({
        action: "update_tax",
        index: parseInt(selectElement.dataset.index),
        tax_mode: selectElement.value, 
        tax_calc_mode: getTaxCalcMode()
    });
}

// 割引変更
function updateDiscount() {
    const discountPrice = parseInt(document.getElementById("discountPrice").value) || 0;
    sendPostRequest({
        action: "update_discount",
        price: discountPrice, 
        tax_calc_mode: getTaxCalcMode()
    });
}

// 行の削除
function deleteItem(button) {
    // 送信前に要素が最新の DOM に存在するかチェック
    if (!isValidElement(button)) return;

    sendPostRequest({
        action: "delete",
        index: parseInt(button.dataset.index), 
        tax_calc_mode: getTaxCalcMode()
    });
}

// 行の追加
function addItem() {
    sendPostRequest({
        action: "add", 
        tax_calc_mode: getTaxCalcMode()
    });
}

// すべての品目の税率を一括変更
function allUpdateTax(selectElement) {
    const tax_mode = selectElement.value;
    if (!tax_mode) return;

    if (confirm("すべての品目の税率を変更しますか？")) {
        sendPostRequest({
            action: "all_update_tax",
            tax_mode: tax_mode,
            tax_calc_mode: getTaxCalcMode()
        });
    } else {
        // キャンセルされた場合はセレクトボックスの表示をリセット
        selectElement.value = "";
    }
}

// キャンセルボタン用の関数
function cancelEditForm() {
    // 確認ポップアップを表示
    if (!confirm('編集内容を破棄しますか？')) {
        return; // キャンセルされたら何もしない
    }

    const form = document.getElementById("editFormSubmit");

    // Flask側が「action == 'cancel'」を判定できるように、hidden inputを生成して追加
    const hiddenInput = document.createElement("input");
    hiddenInput.type = "hidden";
    hiddenInput.name = "action";
    hiddenInput.value = "cancel";
    form.appendChild(hiddenInput);

    // 日付未入力などのHTML5バリデーションによる送信ブロックを強制解除
    form.noValidate = true;

    // フォームを送信（FlaskへPOSTされ、セッション初期化後に /confirmation へ遷移）
    form.submit();
}

// 確認画面へボタン用の関数
function submitEditForm() {
    const form = document.getElementById("editFormSubmit");
    const datetimeInput = document.getElementById("registerDatetime");

    // 日付にエラーがある場合は送信をブロック
    if (datetimeInput && datetimeInput.classList.contains("is-invalid")) {
        alert("日時の入力内容に不備があります。修正してから確認画面へ進んでください。");
        datetimeInput.focus();
        return;
    }

    // Flask側が「action == 'confirm'」を判定できるように hidden input を追加
    const hiddenInput = document.createElement("input");
    hiddenInput.type = "hidden";
    hiddenInput.name = "action";
    hiddenInput.value = "confirm";
    form.appendChild(hiddenInput);

    form.submit();
}