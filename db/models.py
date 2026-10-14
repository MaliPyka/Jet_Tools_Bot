from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, func, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    worker_type: Mapped[str | None] = mapped_column(String, nullable=True)

    shifts: Mapped[list["Shift"]] = relationship(back_populates="user")


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    zone: Mapped[str | None] = mapped_column(String, nullable=True)

    old_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    corrections_count: Mapped[int] = mapped_column(Integer, default=0)
    far_count: Mapped[int] = mapped_column(Integer, default=0)
    battery_count: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String, default="scout", server_default="scout")
    worker_type: Mapped[str] = mapped_column(String, default="night", server_default="night")

    earnings: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="shifts")