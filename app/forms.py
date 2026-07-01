from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, length


class SignUpForm(FlaskForm):
    mailaddress = StringField(
        "メールアドレス",
        validators=[
            DataRequired("メールアドレスは必須です"),
            Email("メールアドレスの形式で入力してください"),
        ],
    )
    # 文字数制限つけた方がいいか？
    password = PasswordField(
        "パスワード", validators=[DataRequired("パスワードは必須です")]
    )
    submit = SubmitField("新規登録")


class LoginForm(FlaskForm):
    mailaddress = StringField(
        "メールアドレス",
        validators=[
            DataRequired("メールアドレスは必須です"),
            Email("メールアドレスの形式で入力してください"),
        ],
    )
    password = PasswordField(
        "パスワード", validators=[DataRequired("パスワードは必須です")]
    )
    submit = SubmitField("ログイン")


class UploadImageForm(FlaskForm):
    image = FileField(
        validators=[
            FileRequired("画像ファイルを指定してください"),
            FileAllowed(["png", "jpg", "jpeg"], "サポートされていない画像形式です"),
        ]
    )
    submit = SubmitField("アップロード")
