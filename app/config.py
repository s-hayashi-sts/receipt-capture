import os

from dotenv import load_dotenv

# .envファイルの内容を環境変数として読み込む
load_dotenv()


class Config:
    # 全環境共通の設定
    SECRET_KEY = os.environ.get("SECRET_KEY")
    WTF_CSRF_SECRET_KEY = os.environ.get("WTF_CSRF_SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///receipt.db")
    MAX_CONTENT_LENGTH = 40 * 1024 * 1024  # リクエスト全体で40MBまで


class DevelopmentConfig(Config):
    # 開発環境用
    DEBUG = True
    SQLALCHEMY_ECHO = True  # SQLをターミナルへ出力する
    DEBUG_TB_INTERCEPT_REDIRECTS = False


class TestingConfig(Config):
    # テスト環境用
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    # 本番環境用
    DEBUG = False
    SQLALCHEMY_ECHO = False
    SESSION_COOKIE_SECURE = True  # HTTPS通信でのみCookieを送信
    SESSION_COOKIE_HTTPONLY = True  # JavaScriptからCookieを読めないようにする


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
