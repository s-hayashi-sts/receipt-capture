from app import app, User, login_user, logout_user, login_required, db
from app.receiptreader import ReceiptReader
from flask import render_template, request, redirect

from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash


#$env:FLASK_APP="hello" ※フォルダ名と揃える！！
#$env:FLASK_ENV="development"
#$env:FLASK_DEBUG = "1"

#sample@sampleaddress.com
#SampleSample00&&



@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mailaddress = request.form.get('mailaddress')
        password = request.form.get('password')

        user = User.query.filter_by(mailaddress=mailaddress).first()
        if check_password_hash(user.password, password):
            login_user(user)#引数のユーザーでログインする   
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


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files.get("file")
        if not file:
            return "ファイルが選択されていません"
        
        receiptreader = ReceiptReader(file)
        receiptreader.file_read()
        return redirect("/upload")
        #return redirect("/confirmation")
    else:
        return render_template("upload.html")


@app.route('/report', methods=['GET', 'POST'])
def report():
    if request.method == 'POST':
        pass
    else:
        return render_template("report.html")
    

@app.route('/confirmation', methods=['GET', 'POST'])
def confirmation():
    if request.method == 'POST':
        pass
    else:
        return render_template("confirmation.html")  