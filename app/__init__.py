from flask import Flask

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer, String, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, relationship

from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required


from datetime import datetime
import pytz

import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///receipt.db"
app.config['SECRET_KEY'] = os.urandom(24)


class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)


login_manager = LoginManager()
login_manager.init_app(app)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    mailaddress: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(200), nullable=False)

    # User → Expense の 1対多
    expenses: Mapped[list["Expense"]] = relationship(back_populates="user")

class Expense(db.model):
    __tablename__ = "expenses"

    id:Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    item: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # Expense → User の逆参照
    user: Mapped["User"] = relationship(back_populates="expenses")

@login_manager.user_loader#書くだけでいい
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
   db.create_all()

from app import main