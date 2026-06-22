import logging
from flask_debugtoolbar import DebugToolbarExtension
from app import app, User, Receipt, Expense, db
from app.receiptreader import ReceiptReader
from flask import render_template, request, redirect, flash, session, jsonify
from flask_login import current_user,  UserMixin, LoginManager, login_user, logout_user, login_required
from flask_bootstrap import Bootstrap
import secrets
from datetime import datetime, date
from sqlalchemy import func
import math
import copy
from email_validator import validate_email, EmailNotValidError
from werkzeug.security import generate_password_hash, check_password_hash


#$env:FLASK_APP="hello" ※フォルダ名と揃える！！
#$env:FLASK_ENV="development"
#$env:FLASK_DEBUG = "1"

#sample@sampleaddress.com
#SampleSample00&&

app.logger.setLevel(logging.debug)

app.secret_key = "sample_key"#.envファイルに置く
# リダイレクトを中断しないようにする
app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False
# DebugToolbarExtensionにアプリケーションをセットする
toolbar = DebugToolbarExtension(app)


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mailaddress = request.form.get('mailaddress')
        password = request.form.get('password')

        user = User.query.filter_by(mailaddress=mailaddress).first()
        if check_password_hash(user.password, password):
            login_user(user)#引数のユーザーでログインする 
            print("認証状態:", current_user.is_authenticated)#ログイン確認
            print("ユーザー中身:", current_user)
            return redirect('/upload')
        #実際はユーザーが見つからない場合などの例外処理を入れる
    else:
        return render_template("login.html")


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        mailaddress = request.form.get('mailaddress')
        password = request.form.get('password')

        #入力チェック
        if not mailaddress or not password:
            return render_template("signup.html",error="メールアドレスとパスワードは必須です" )
        
        if len(password) < 8:
            return render_template("signup.html",error="パスワードは8文字以上にしてください" )
        
        #最低大文字小文字が１文字ずつ必要

        #最低一文字の数字が必要

        #最低一文字の記号が必要
        
        if User.query.filter_by(mailaddress=mailaddress).first():
            return render_template("signup.html", error="このメールアドレスは既に登録されています")

        user = User(mailaddress=mailaddress, password=generate_password_hash(password, method='pbkdf2:sha256'))

        db.session.add(user)
        db.session.commit()
        return redirect('/')
    else:
        return render_template("signup.html")   

def validationCheck(mailaddress, password):
    # 入力チェック
    is_valid = True

    if not mailaddress or not password:
        flash("メールアドレスとパスワードは必須です")
        is_vaild = False
    
    try:
        validate_email(mailaddress)
    except EmailNotValidError:
        flash("メールアドレスの形式で入力してください")
        is_vaild = False
    
    return is_vaild
    



@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files.get("file")
        if not file:
            return "ファイルが選択されていません"
        
        receiptreader = ReceiptReader(file)
        image_bytes = receiptreader.deskew()
        annotation = receiptreader.file_read(image_bytes)
        receiptreader.reconstruct_lines(annotation)

        return redirect("/confirmation")
    else:
        return render_template("upload.html")


@app.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    if request.method == 'POST':
        pass
    else:
        return render_template("report.html")

@app.route('/api/monthly-summary', methods=['GET'])
@login_required
def get_monthly_summary():
    """指定された年月の『日ごとの合計金額』を返すAPI"""
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    
    # 指定年月の1日〜末日までのReceiptをクエリ
    # ユーザーごとに絞り込むため、current_user.id を使用
    receipts = (
        db.session.query(
            func.date(Receipt.date).label('day'),
            func.sum(Receipt.total_price).label('daily_total')
        )
        .filter(Receipt.user_id == current_user.id)
        .filter(func.extract('year', Receipt.date) == year)
        .filter(func.extract('month', Receipt.date) == month)
        .group_by(func.date(Receipt.date))
        .all()
    )
    
    # { "2026-06-01": 3467, "2026-06-05": 1200 } のような辞書を作る
    summary_data = {}
    for r in receipts:
        # エラー対策: r.day が文字列ならそのまま、date型なら strftime を使う
        print("value:", r.day, "type", type(r.day)) #debug
        if isinstance(r.day, str):
            # もし '2026-06-21 00:00:00' のようにスペース以降がある場合の考慮
            key = r.day.split()[0] 
        else:
            key = r.day.strftime('%Y-%m-%d')
        summary_data[key] = int(r.daily_total)
    #summary_data = { r.day.strftime('%Y-%m-%d'): int(r.daily_total) for r in receipts }
    return jsonify(summary_data)

@app.route('/api/daily-detail', methods=['GET'])
@login_required
def get_daily_detail():
    """選択された日付の『商品内訳リストとレシート合計』を返すAPI"""
    target_date_str = request.args.get('date') # '2026-06-01'
    if not target_date_str:
        return jsonify({"error": "Missing date"}), 400
    
    # フロントから送られてくる文字列の「最初の10文字（YYYY-MM-DD）」だけを安全に切り出す
    target_date_str = target_date_str[:10]
    target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    
    # その日のユーザーのレシートをすべて取得（明細も一緒にロード）
    receipts = (
        db.session.query(Receipt)
        .filter(Receipt.user_id == current_user.id)
        .filter(func.date(Receipt.date) == target_date)
        .all()
    )
    
    total_price = sum(r.total_price for r in receipts)
    
    # 内訳(Expense)のリストを作成
    items_list = []
    for r in receipts:
        for e in r.expenses:
            items_list.append({
                "item": e.item,
                "price": e.price
            })
            
    return jsonify({
        "date": target_date_str,
        "total_price": total_price,
        "items": items_list
    })
    

@app.route('/edit', methods=['GET', 'POST'])
def edit():
    tax_calc_mode = session.get("tax_calc_mode", "all")
    items = session.get("receipt_items", [])
    discount = session.get("discount", {})
    tax = session.get("tax", [])
    total = session.get("total_amount", {})
    if request.method == 'POST':
        action = request.form.get("action")

        #キャンセル → 編集内容を破棄して /confirmation に戻る
        if action == "cancel":
            #セッションの初期化
            session["tax_calc_mode"] = {"tax_calc_mode":"all"}
            session["receipt_items"] = copy.deepcopy(session["base_receipt_items"])
            session["discount"] = copy.deepcopy(session["base_discount"])
            session["tax"] = copy.deepcopy(session["base_tax"])
            session["total_amount"] = copy.deepcopy(session["base_total_amount"])

            return redirect("/confirmation")
        
        #確認ボタン → バリデーションチェックOKなら /confirmation へ
        if action == "confirm":
            discount = discount["price"]
            error = None

            for i, item in enumerate(items):
                name = item["name"]
                price = item["price"]

                #バリデーション(品目)
                if not name or len(name) > 50:
                    error = "品目は50文字以内で入力してください"
                    break
                #バリデーション(価格、割引)　整数であることを確認
                if not isinstance(price, int):
                    error = "価格は0〜999999の整数で入力してください"
                    break

                #バリデーション(価格、割引)
                if not (0 <= price <= 999999) or not (0 <= discount <= 999999):
                    error = "価格は0〜999999の整数で入力してください"
            
            if error:
                return render_template("edit.html", tax_calc_mode=tax_calc_mode, items=items, discount=discount, tax=tax, total=total, error=error)

            return redirect("/confirmation")
    else:
        return render_template("edit.html", tax_calc_mode=tax_calc_mode, items=items, discount=discount, tax=tax, total=total)


@app.route("/edit/update", methods=["POST"])
def edit_update():
    data = request.get_json()
    action = data.get("action")
    items = session.get("receipt_items", [])
    discount = session.get("discount", {"name": "割引", "price": 0})
    tax_calc_mode = data.get("tax_calc_mode")

    #行の削除
    if action == "delete":
        index = data.get("index")
        if 0 <= index < len(items):
            items.pop(index)

    #行の追加
    elif action == "add":
        items.append({"name": "", "price": 0, "tax_mode": "default"})
    
    #inputBOXへの価格入力
    elif action == "update_price":
        index = data.get("index")
        price = data.get("price", 0)
        items[index]["price"] = price
    
    #inputBOXへの品目入力
    elif action == "update_name":
        index = data.get("index")
        name = data.get("name", "")
        items[index]["name"] = name

    #税率変更
    elif action == "update_tax":
        index = data.get("index")
        tax_mode = data.get("tax_mode")
        items[index]["tax_mode"] = tax_mode
    
    #税率の計算方法の変更
    elif action == "change_calc_mode":
        session["tax_calc_mode"] = tax_calc_mode
    
    #割引変更
    elif action == "update_discount":
        discount["price"] = data.get("price", 0)
    
    #セッション更新
    session["receipt_items"] = items
    session["discount"] = discount

    #合計計算
    total = 0
    subtotal_8 = 0# 税率8%価格の小計
    subtotal_10 = 0# 税率10%価格の小計
    subtotal_tax8 = 0# 税率8% 税金額
    subtotal_tax10 = 0# 税率10% 税金額

    if tax_calc_mode == 'all':
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
        #個別に各品に税率を適用
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
    session["tax"] = [{"name": "外税 8%", "price":subtotal_tax8}, 
                        {"name":"外税 10%", "price":subtotal_tax10}]

    html = render_template("edit_table.html",tax_calc_mode=tax_calc_mode, items=items, discount=discount,tax=session["tax"], total=session["total_amount"])
    return jsonify({"html": html})


@app.route("/confirmation", methods=['GET', 'POST'])
def confirmation():

    if request.method == 'POST':
        action = request.form.get("action")

        #キャンセルボタンを押した場合
        if action == "cancel":
            #セッションをクリア
            clear_edit_session()
            return redirect("/upload")

        #編集ボタンを押した場合
        if action == "edit":
            return redirect("/edit")

        #登録ボタンを押した場合 → DBへ登保存
        if action == "register":
            items = session.get("receipt_items", [])
            discount = session.get("discount", 0)
            tax_items = session.get("tax", [])
            tax = sum(i.get("price", 0) for i in tax_items) # 税金の合計額
            total = session.get("total_amount", 0)
            #日時の取得(本番ではレシートから取得したい)
            register_date = datetime.now()

            #DBへ保存
            #Receipt 情報
            new_receipt = Receipt(
                user_id = current_user.id, 
                total_price = total["price"], 
                tax = tax, 
                discount = discount["price"], 
                date = register_date
            )

            #Expence 情報
            for item in items:
                expense = Expense(
                    receipt = new_receipt, 
                    item = item["name"],
                    price = item["price"]
                )
                db.session.add(expense)

            db.session.add(new_receipt)
            db.session.commit()

            #セッションをクリア
            clear_edit_session()

            return redirect("/upload")
    else:
        items = session.get("receipt_items", [])
        discount = session.get("discount", {})
        tax = session.get("tax", [])
        total = session.get("total_amount", {})
        return render_template("confirmation.html", items=items, discount=discount, tax=tax, total=total)
        
#セッションを削除する関数
def clear_edit_session():
    EDIT_SESSION_KEYS = [
        "discount",
        "tax",
        "receipt_items",
        "total_amount",
        "base_receipt_items",
        "base_discount",
        "base_tax",
        "base_total_amount"
    ]
    for key in EDIT_SESSION_KEYS:
        session.pop(key, None)