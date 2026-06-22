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
app.config['SECRET_KEY'] = "sample_key"
#os.urandom(24)


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
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="user")

class Receipt(db.Model):
    __tablename__ = "receipts"
    id:Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # レシート全体の金額情報
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)  # 合計金額
    tax: Mapped[int] = mapped_column(Integer, default=0)              # 税額
    discount: Mapped[int] = mapped_column(Integer, default=0)         # 割引額

    # 買い物した日時（明細ごとではなくレシート単位で管理）
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # リレーション設定
    user: Mapped["User"] = relationship(back_populates="receipts")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="receipt", cascade="all, delete-orphan")

class Expense(db.Model):
    __tablename__ = "expenses"

    id:Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), nullable=False)
    item: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)

    # リレーション設定
    receipt: Mapped["Receipt"] = relationship(back_populates="expenses")

@login_manager.user_loader#書くだけでいい
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
   db.create_all()

from app import main