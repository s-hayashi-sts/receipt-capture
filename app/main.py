import logging
import os
import tempfile

from flask import Flask, render_template
from flask_debugtoolbar import DebugToolbarExtension
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect
from sqlalchemy.orm import DeclarativeBase

from app.config import config_by_name

# Renderの環境変数からGoogle認証JSON文字列を取得
google_credentials_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

if google_credentials_json:
    # 一時ファイルを作成してJSONの中身を書き込む
    temp_credentials_file = tempfile.NamedTemporaryFile(
        delete=False, mode="w", suffix=".json"
    )
    temp_credentials_file.write(google_credentials_json)
    temp_credentials_file.close()

    # GCPクライアントライブラリが参照する環境変数をセット
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_credentials_file.name

app = Flask(__name__)

# 環境変数 FLASK_ENV の値（development / testing / production）に応じてconfigを切り替える
env_name = os.environ.get("FLASK_ENV", "development")
app.config.from_object(config_by_name[env_name])

csrf = CSRFProtect(app)
app.logger.setLevel(logging.DEBUG if app.config["DEBUG"] else logging.INFO)


# カスタムエラー画面を表示する関数
def page_not_found(e):
    """404 Not found"""
    return render_template("404.html"), 404


def internal_server_error(e):
    """500 Internal Server Error"""
    return render_template("500.html"), 500


def request_entity_too_large(e):
    """413 Request Entity Too Large"""
    return render_template("413.html"), 413


@app.errorhandler(CSRFError)
def csrf_error(e):
    # CSRF期限切れ
    return (render_template("400_csrf_error.html"), 400)


# カスタムエラー画面を登録
app.register_error_handler(404, page_not_found)
app.register_error_handler(500, internal_server_error)
app.register_error_handler(413, request_entity_too_large)


# Debug Toolbarは開発環境でのみ有効化
if app.config["DEBUG"]:
    toolbar = DebugToolbarExtension(app)


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)

Migrate(app, db)

"""開発中のみ使用"""
if env_name == "development":
    with app.app_context():
        db.create_all()

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = ""
login_manager.init_app(app)
