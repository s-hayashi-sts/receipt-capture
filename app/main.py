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

"""
VisionAPIを使用するための認証情報を環境変数から取得し、
GCPクライアントライブラリが参照する環境変数にセットする処理
"""
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


# 拡張機能のインスタンスを定義（トップレベル）
class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app():
    """Flaskアプリケーションのインスタンスを作成するファクトリ関数"""
    app = Flask(__name__)

    # 環境変数 FLASK_ENV の値に応じてconfigを切り替える
    env_name = os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_by_name[env_name])

    # 各種拡張機能をアプリにバインド
    csrf.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "login"
    login_manager.login_message = ""
    login_manager.init_app(app)

    app.logger.setLevel(logging.DEBUG if app.config["DEBUG"] else logging.INFO)

    # カスタムエラー画面を表示する関数定義
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
        DebugToolbarExtension(app)

    # Blueprintの登録
    from app.views import bp
    app.register_blueprint(bp)

    # アプリケーションコンテキスト内でモデルを読み込み、DB初期化を行う
    with app.app_context():
        # モデル定義を読み込むことでSQLAlchemyにモデルを登録する（パスは実際の構成に合わせて変更してください）
        from app import models

        if env_name == "development":
            db.create_all()

    return app


# WSGIサーバーや flask run などが呼び出すためのアプリインスタンスを作成
app = create_app()