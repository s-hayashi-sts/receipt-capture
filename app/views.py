import copy
import math
from datetime import date, datetime

from flask import flash, jsonify, redirect, render_template, request, session
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import String, cast, func
from werkzeug.security import check_password_hash, generate_password_hash

from apps.app.api_limiter import check_api_usage
from apps.app.forms import LoginForm, SignUpForm, UploadImageForm
from apps.app.main import app, db
from apps.app.models import Expense, Receipt, User
from apps.app.receiptreader import ReceiptReader, ReceiptValidationError


@app.route("/", methods=["GET", "POST"])
def login():
    # 既にログイン済みの場合は /upload へリダイレクト
    if current_user.is_authenticated:
        return redirect("/upload")

    form = LoginForm()
    if request.method == "POST":
        if form.validate_on_submit():
            user = User.query.filter_by(mailaddress=form.mailaddress.data).first()
            if user is not None and check_password_hash(
                user.password, form.password.data
            ):
                login_user(user)  # 引数のユーザーでログインする

                # GETパラメータにnextキーが存在し、値がない場合は /upload ページへ
                next_ = request.args.get("next")
                if next_ is None or not next_.startswith("/"):
                    next_ = "/upload"
                return redirect(next_)

        flash("メールアドレスかパスワードが不正です")
    return render_template("login.html", form=form)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = SignUpForm()

    if request.method == "POST":
        if form.validate_on_submit():
            # メールアドレスの重複チェック
            if User.query.filter_by(mailaddress=form.mailaddress.data).first():
                flash("指定のメールアドレスは既に登録されています")
                return render_template("signup.html", form=form)

            user = User(
                mailaddress=form.mailaddress.data,
                password=generate_password_hash(
                    form.password.data, method="pbkdf2:sha256"
                ),
            )

            db.session.add(user)
            db.session.commit()
            return redirect("/")
        else:
            return render_template("signup.html", form=form)

    else:
        return render_template("signup.html", form=form)


@app.route("/logout")
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect("/")


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    # セッションをクリアする
    clear_edit_session()
    clear_base_session()
    session.pop("to_succeed", False)
    session.pop("from_report", False)
    # フラグの発行
    session["to_edit"] = True

    form = UploadImageForm()
    if request.method == "POST" and form.validate_on_submit():
        file = form.image.data
        try:
            receiptreader = ReceiptReader(file)

            # 前処理
            image_bytes = receiptreader.deskew_and_adjustment()
            # API利用上限のチェック
            success, error_msg = check_api_usage()
            if not success:
                flash(error_msg)
                return render_template("upload.html", form=form)

            # Vision APIの実行
            annotation = receiptreader.file_read(image_bytes)
            # 文字認識の信頼度スコアのチェック
            receiptreader.check_confidence(annotation)
            # フォーマットチェックおよびデータ整形
            receiptreader.reconstruct_lines(annotation)

            # フラグを発行
            session["to_confirmation"] = True

            return redirect("/confirmation")

        except ReceiptValidationError as e:
            # カスタムエラーが発生した場合は、メッセージを画面に表示して再描画
            flash(str(e))
            return render_template("upload.html", form=form)

        except Exception as e:
            # その他の予期せぬエラー（APIエラーなど）のハンドリング
            flash(
                "システムの処理中にエラーが発生しました。時間を置いて再度お試しください。"
            )
            print(f"Unexpected Error: {e}")  # デバッグ用にコンソールへ出力
            return render_template("upload.html", form=form)

    return render_template("upload.html", form=form)


@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    # セッションをクリアする
    clear_edit_session()
    clear_base_session()
    # 画面遷移フラグの制限
    session["from_report"] = True
    session.pop("to_edit", False)
    session.pop("to_confirmation", False)
    session.pop("to_succeed", False)

    if request.method == "POST":
        pass
    else:
        return render_template("report.html")


@app.route("/api/monthly-summary", methods=["GET"])
@login_required
def get_monthly_summary():
    """指定された年月の『日ごとの合計金額』を返すAPI"""
    # 不正な画面遷移の場合は/reportへ遷移
    if not session.get("from_report", False):
        return redirect("/report")

    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))

    # 指定年月の1日〜末日までのReceiptをクエリ
    # ユーザーごとに絞り込むため、current_user.id を使用
    receipts = (
        db.session.query(
            cast(func.date(Receipt.date), String).label("day"),
            func.sum(Receipt.total_price).label("daily_total"),
        )
        .filter(Receipt.user_id == current_user.id)
        .filter(func.extract("year", Receipt.date) == year)
        .filter(func.extract("month", Receipt.date) == month)
        .group_by("day")
        .all()
    )

    # { "2026-06-01": 3467, "2026-06-05": 1200 } のような辞書を作る
    summary_data = {}
    for r in receipts:
        if not r.day:
            continue
        # エラー対策: 文字列型でない場合は文字列型へ変換
        if isinstance(r.day, (date, datetime)):
            key = r.day.strftime("%Y-%m-%d")
        else:
            # すでに文字列（またはキャスト済み）の場合は文字列化して前後の空白を除去
            key = str(r.day).strip()

        # "YYYY-MM-DD" のフォーマットになっているか簡易検証して辞書に格納
        if len(key) >= 10:
            # "YYYY-MM-DD HH:MM:SS" などが付与されて返された場合への安全対策
            key = key[:10]
            summary_data[key] = int(r.daily_total)
    # summary_data = { r.day.strftime('%Y-%m-%d'): int(r.daily_total) for r in receipts }
    return jsonify(summary_data)


@app.route("/api/daily-detail", methods=["GET"])
@login_required
def get_daily_detail():
    """選択された日付の『商品内訳リストとレシート合計』を返すAPI"""
    # 不正な画面遷移の場合は/reportへ遷移
    if not session.get("from_report", False):
        return redirect("/report")

    target_date_str = request.args.get("date")  # '2026-06-01'
    if not target_date_str:
        return jsonify({"error": "Missing date"}), 400

    # フロントから送られてくる文字列の「最初の10文字（YYYY-MM-DD）」だけを切り出す
    target_date_str = target_date_str[:10]
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    # その日のユーザーのレシートをすべて取得（明細も一緒にロード）
    receipts = (
        db.session.query(Receipt)
        .filter(Receipt.user_id == current_user.id)
        .filter(func.date(Receipt.date) == target_date)
        .all()
    )

    # 内訳(Expense)のリストを作成
    items_list = []
    total_price = 0
    total_tax = 0

    for r in receipts:
        for e in r.expenses:
            items_list.append({"item": e.item, "price": e.price})
        # 合計金額・合計消費税の加算
        total_price += r.total_price or 0
        total_tax += r.tax or 0

        # discountが存在する場合、個別項目（"割引"）としてリストに追加
        if r.discount and r.discount > 0:
            items_list.append(
                {
                    "item": "割引",
                    "price": -r.discount,  # マイナス表記
                }
            )

    return jsonify(
        {
            "date": target_date_str,
            "total_price": total_price,
            "total_tax": total_tax,
            "items": items_list,
        }
    )


@app.route("/api/date-range", methods=["GET"])
@login_required
def get_date_range():
    """DBに登録されている、このユーザーの最も古いレシート日付の年月を返す"""
    # 不正な画面遷移の場合は/reportへ遷移
    if not session.get("from_report", False):
        return redirect("/report")

    earliest = (
        db.session.query(func.min(Receipt.date))
        .filter(Receipt.user_id == current_user.id)
        .scalar()
    )
    now = datetime.now()
    if earliest is None:
        # データが1件もない場合は当月を最古扱いにする
        return jsonify({"earliest_year": now.year, "earliest_month": now.month})

    if isinstance(earliest, str):
        # 環境によって文字列で返る場合があるための保険
        earliest = datetime.strptime(earliest[:19], "%Y-%m-%d %H:%M:%S")

    return jsonify({"earliest_year": earliest.year, "earliest_month": earliest.month})


def check_validation():
    items = session.get("receipt_items", [])
    discount = session.get("discount", {})
    total = session.get("total_amount", {})

    for i, item in enumerate(items):
        name = item["name"]
        price = item["price"]

        # バリデーション(品目)
        if not name or len(name) > 50:
            return "品目は50文字以内で入力してください"
        # バリデーション(価格)　整数であることを確認
        if not isinstance(price, int) or not (0 <= price <= 999999):
            return "価格は0〜999999の整数で入力してください"

    # バリデーション（割引）
    if not isinstance(discount["price"], int) or not (0 <= discount["price"] <= 999999):
        return "割引は0〜999999の整数で入力してください"

    # バリデーション（合計）
    if total["price"] < 0:
        return "合計金額がマイナスになっています"

    return None


@app.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    # 正規ルートでの遷移かどうか確認（フラグがない場合アップロード画面へ飛ばす）
    if not session.get("to_edit", False):
        return redirect("/upload")

    # セッション
    register_datetime = session.setdefault(
        "register_datetime",
        {"name": "登録日時", "datetime": datetime.now().strftime("%Y-%m-%d %H:%M")},
    )
    tax_calc_mode = session.setdefault("tax_calc_mode", "all")
    items = session.setdefault(
        "receipt_items", [{"name": "", "price": 0, "tax_mode": "default"}]
    )
    discount = session.setdefault(
        "discount",
        {
            "name": "割引",
            "price": 0,
        },
    )
    tax = session.setdefault(
        "tax",
        [
            {"name": "外税 8%", "price": 0},
            {"name": "外税 10%", "price": 0},
        ],
    )
    total = session.setdefault("total_amount", {"name": "合計", "price": 0})

    # 初期化セッションがない場合（手動入力で遷移した場合）
    if not session.get("base_register_datetime", False):
        session["base_register_datetime"] = register_datetime
        session["base_receipt_items"] = items
        session["base_discount"] = discount
        session["base_tax"] = tax
        session["base_total_amount"] = total

    if request.method == "POST":
        action = request.form.get("action")

        # キャンセル → 編集内容を破棄して /confirmation に戻る
        if action == "cancel":
            # セッションの初期化
            session["register_datetime"] = copy.deepcopy(
                session["base_register_datetime"]
            )
            session["tax_calc_mode"] = "all"
            session["receipt_items"] = copy.deepcopy(session["base_receipt_items"])
            session["discount"] = copy.deepcopy(session["base_discount"])
            session["tax"] = copy.deepcopy(session["base_tax"])
            session["total_amount"] = copy.deepcopy(session["base_total_amount"])

            # フラグの制御
            session["to_confirmation"] = True
            session["to_edit"] = False
            return redirect("/confirmation")

        # 確認ボタン → バリデーションチェックOKなら /confirmation へ
        if action == "confirm":
            # バリデーションチェック
            error = check_validation()

            if error:
                return render_template(
                    "edit.html",
                    register_datetime=register_datetime,
                    tax_calc_mode=tax_calc_mode,
                    items=items,
                    discount=discount,
                    tax=tax,
                    total=total,
                    error=error,
                )

            # フラグの発効
            session["to_confirmation"] = True
            session["to_edit"] = False

            return redirect("/confirmation")
    else:
        return render_template(
            "edit.html",
            register_datetime=register_datetime,
            tax_calc_mode=tax_calc_mode,
            items=items,
            discount=discount,
            tax=tax,
            total=total,
        )


@app.route("/edit/update", methods=["POST"])
@login_required
def edit_update():
    data = request.get_json()
    action = data.get("action")
    items = session.get("receipt_items", [])
    discount = session.get("discount", {"name": "割引", "price": 0})
    tax_calc_mode = data.get("tax_calc_mode", "all")

    # 日時の変更
    if action == "update_datetime":
        new_dt = data.get("datetime")
        # セッションの register_datetime (辞書型) 内の datetime を上書き
        session["register_datetime"] = {"name": "登録日時", "datetime": new_dt}

    # 行の削除
    if action == "delete":
        index = data.get("index")
        if 0 <= index < len(items):
            items.pop(index)

    # 行の追加
    elif action == "add":
        items.append({"name": "", "price": 0, "tax_mode": "default"})

    # inputBOXへの価格入力
    elif action == "update_price":
        index = data.get("index")
        if index is not None and 0 <= index < len(items):
            items[index]["price"] = data.get("price", 0)

    # inputBOXへの品目入力
    elif action == "update_name":
        index = data.get("index")
        if index is not None and 0 <= index < len(items):
            items[index]["name"] = data.get("name", "")

    # 税率変更
    elif action == "update_tax":
        index = data.get("index")
        if index is not None and 0 <= index < len(items):
            items[index]["tax_mode"] = data.get("tax_mode")

    elif action == "all_update_tax":
        tax_mode = data.get("tax_mode")
        for item in items:
            item["tax_mode"] = tax_mode

    # 税率の計算方法の変更
    elif action == "change_calc_mode":
        session["tax_calc_mode"] = tax_calc_mode

    # 割引変更
    elif action == "update_discount":
        discount["price"] = data.get("price", 0)

    # セッション更新
    session["receipt_items"] = items
    session["discount"] = discount

    # 合計計算
    total = 0
    subtotal_8 = 0  # 税率8%品目の小計
    subtotal_10 = 0  # 税率10%品目の小計
    subtotal_tax8 = 0  # 税率8% 税金額
    subtotal_tax10 = 0  # 税率10% 税金額

    if tax_calc_mode == "all":  # 税抜きの合計額に税率をかける
        for item in items:
            total += item["price"]
            if item["tax_mode"] == "tax8":
                subtotal_8 += item["price"]
            elif item["tax_mode"] == "tax10":
                subtotal_10 += item["price"]
        subtotal_tax8 = math.floor(subtotal_8 * 0.08)
        subtotal_tax10 = math.floor(subtotal_10 * 0.10)
        total = total + subtotal_tax8 + subtotal_tax10
    else:
        # 個別に各品に税率を適用
        for item in items:
            if item["tax_mode"] == "tax8":
                tax_value = math.floor(item["price"] * 0.08)
                total += item["price"] + tax_value
                subtotal_tax8 += tax_value
            elif item["tax_mode"] == "tax10":
                tax_value = math.floor(item["price"] * 0.10)
                subtotal_tax10 += tax_value
                total += item["price"] + tax_value
            else:
                total += item["price"]

    total = total - discount["price"]
    session["total_amount"] = {"name": "合計", "price": total}
    session["tax"] = [
        {"name": "外税 8%", "price": subtotal_tax8},
        {"name": "外税 10%", "price": subtotal_tax10},
    ]

    html = render_template(
        "edit_table.html",
        tax_calc_mode=tax_calc_mode,
        items=items,
        discount=discount,
        tax=session["tax"],
        total=session["total_amount"],
    )
    return jsonify({"html": html})


@app.route("/confirmation", methods=["GET", "POST"])
@login_required
def confirmation():
    # 正規ルートでの遷移かどうか確認（フラグがない場合アップロード画面へ飛ばす）
    if not session.get("to_confirmation", False):
        return redirect("/upload")

    register_datetime = session.get("register_datetime", {})
    items = session.get("receipt_items", [])
    discount = session.get("discount", {})
    tax = session.get("tax", [])
    total = session.get("total_amount", {})

    if request.method == "POST":
        action = request.form.get("action")

        # キャンセルボタンを押した場合
        if action == "cancel":
            # セッションをクリア
            clear_edit_session()
            clear_base_session()
            # フラグを制限
            session["to_confirmation"] = False

            return redirect("/upload")

        # 編集ボタンを押した場合
        if action == "edit":
            # フラグを発行
            session["to_confirmation"] = False
            session["to_edit"] = True

            return redirect("/edit")

        # 登録ボタンを押した場合 → DBへ保存
        if action == "register":
            # バリデーションチェック
            error = check_validation()
            if error:
                return render_template(
                    "confirmation.html",
                    register_datetime=register_datetime,
                    items=items,
                    discount=discount,
                    tax=tax,
                    total=total,
                    error=error,
                )

            # 税金の合計額
            tax_total = sum(i.get("price", 0) for i in tax)
            # セッションから取得した日時データをパースする
            date_val = register_datetime.get("datetime")
            if isinstance(date_val, str):
                # 文字列（"YYYY-MM-DD HH:MM"）から Pythonの datetime オブジェクトに変換
                db_date = datetime.strptime(date_val, "%Y-%m-%d %H:%M")
            elif date_val:
                db_date = date_val
            else:
                # 万が一取得できなかった場合のフォールバック（現在日時）
                db_date = datetime.now()

            # DBへ保存
            # Receipt 情報
            new_receipt = Receipt(
                user_id=current_user.id,
                total_price=total["price"],
                tax=tax_total,
                discount=discount["price"],
                date=db_date,
            )

            # Expence 情報
            for item in items:
                expense = Expense(
                    receipt=new_receipt, item=item["name"], price=item["price"]
                )
                db.session.add(expense)

            db.session.add(new_receipt)
            db.session.commit()

            # セッションをクリア
            clear_edit_session()
            clear_base_session()

            # フラグを制限
            session["to_confirmation"] = False
            session["to_succeed"] = True

            return redirect("/succeed")
    else:
        return render_template(
            "confirmation.html",
            register_datetime=register_datetime,
            items=items,
            discount=discount,
            tax=tax,
            total=total,
        )


@app.route("/succeed", methods=["GET"])
@login_required
def succeed():
    # 正規ルートでの遷移かどうか確認（フラグがない場合アップロード画面へ飛ばす）
    if not session.get("to_succeed", False):
        return redirect("/upload")

    return render_template("succeed.html")


# セッションを削除する関数
def clear_edit_session():
    EDIT_SESSION_KEYS = [
        "register_datetime",
        "discount",
        "tax",
        "receipt_items",
        "total_amount",
        "base_receipt_items",
        "base_discount",
        "base_tax",
        "base_total_amount",
    ]
    for key in EDIT_SESSION_KEYS:
        session.pop(key, None)


def clear_base_session():
    BASE_SESSION_KEYS = [
        "base_register_datetime",
        "base_receipt_items",
        "base_discount",
        "base_tax",
        "base_total_amount",
    ]
    for key in BASE_SESSION_KEYS:
        session.pop(key, None)
