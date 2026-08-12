from datetime import datetime
from zoneinfo import ZoneInfo

from flask_login import UserMixin
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.main import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    mailaddress: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(200), nullable=False)

    # User → Expense の 1対多
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="user")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Receipt(db.Model):
    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # レシート全体の金額情報
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)  # 合計金額
    tax: Mapped[int] = mapped_column(Integer, default=0)  # 税額（税別の場合）
    discount: Mapped[int] = mapped_column(Integer, default=0)  # 割引額

    # 買い物した日時（レシート単位で管理）
    date: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(ZoneInfo("Asia/Tokyo")))

    # リレーション設定
    user: Mapped["User"] = relationship(back_populates="receipts")
    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class Expense(db.Model):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), nullable=False)
    item: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)

    # リレーション設定
    receipt: Mapped["Receipt"] = relationship(back_populates="expenses")


class ApiUsage(db.Model):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    # "2026-07" のような年月文字列で管理する
    year_month: Mapped[str] = mapped_column(String(7), unique=True, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)