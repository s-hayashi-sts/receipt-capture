import logging

from flask import Flask
from flask_debugtoolbar import DebugToolbarExtension
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase

csrf = CSRFProtect()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///receipt.db"
app.config["SECRET_KEY"] = "sample_key"
# os.urandom(24)
app.config["SQLAlchemy_ECHO"] = True
app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False  # リダイレクトを中断しないようにする
app.config["WTF_CSRF_SECRET_KEY"] = "samplesampesamplesample"

app.logger.setLevel(logging.DEBUG)

# DebugToolbarExtensionにアプリケーションをセットする
toolbar = DebugToolbarExtension(app)


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)

Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = "app/signup"
login_manager.login_message = ""
login_manager.init_app(app)
