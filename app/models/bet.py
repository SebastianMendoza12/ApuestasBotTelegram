from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class BetStatus(str, PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"
    VOID = "void"


class BetType(str, PyEnum):
    SINGLE = "single"
    ACCUMULATOR = "accumulator"
    SYSTEM = "system"
    LIVE = "live"


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    bet_id_external: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    bet_type: Mapped[BetType] = mapped_column(Enum(BetType), nullable=False)
    status: Mapped[BetStatus] = mapped_column(Enum(BetStatus), default=BetStatus.PENDING, nullable=False)

    stake: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    potential_return: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    actual_return: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)

    odds: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=4), nullable=False)
    sport: Mapped[str] = mapped_column(String(100), nullable=False)
    league: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_name: Mapped[str] = mapped_column(String(500), nullable=False)
    event_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    selection: Mapped[str] = mapped_column(Text, nullable=False)
    selection_odds: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=4), nullable=False)

    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="bets", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("user_id", "bet_id_external", name="uq_bets_user_external"),
    )

    def __repr__(self) -> str:
        return f"<Bet(id={self.id}, user_id={self.user_id}, status={self.status}, stake={self.stake})>"