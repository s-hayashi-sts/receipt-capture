from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired, FileSize
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Regexp


class SignUpForm(FlaskForm):
    mailaddress = StringField(
        "メールアドレス",
        validators=[
            DataRequired("メールアドレスは必須です"),
            Email("メールアドレスの形式で入力してください"),
            Length(max=30),
        ],
        filters=[lambda x: x.strip() if x else x],
    )
    password = PasswordField(
        "パスワード",
        validators=[
            DataRequired("パスワードは必須です"),
            Length(
                min=8,
                max=100,
                message="パスワードは8文字以上100文字以内で入力してください",
            ),
            Regexp(
                r"^[!-~]+$",
                message="パスワードは半角英数字・記号のみで入力してください",
            ),
        ],
        filters=[lambda x: x.strip() if x else x],
    )
    submit = SubmitField("新規登録")


class LoginForm(FlaskForm):
    mailaddress = StringField(
        "メールアドレス",
        validators=[
            DataRequired("メールアドレスは必須です"),
            Email("メールアドレスの形式で入力してください"),
            Length(max=30),
        ],
        filters=[lambda x: x.strip() if x else x],
    )
    password = PasswordField(
        "パスワード",
        validators=[
            DataRequired("パスワードは必須です"),
            Length(
                min=8,
                max=100,
                message="パスワードは8文字以上100文字以内で入力してください",
            ),
        ],
        filters=[lambda x: x.strip() if x else x],
    )
    submit = SubmitField("ログイン")


class UploadImageForm(FlaskForm):
    image = FileField(
        validators=[
            FileRequired("画像ファイルを指定してください"),
            FileAllowed(["png", "jpg", "jpeg"], "サポートされていない画像形式です"),
            FileSize(
                max_size=30 * 1024 * 1024,  # 30MBまで
                message="ファイルサイズは30MB以内にしてください",
            ),
        ]
    )
    submit = SubmitField("画像をアップロード")
