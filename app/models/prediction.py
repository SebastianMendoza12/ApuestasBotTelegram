from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class PredictionStatus(str, PyEnum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    league: Mapped[str | None] = mapped_column(String(200), nullable=True)
    home_team: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team: Mapped[str] = mapped_column(String(255), nullable=False)
    event_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    market: Mapped[str] = mapped_column(String(50), default="h2h", nullable=False)
    market_key: Mapped[str] = mapped_column(String(50), default="h2h", nullable=False)
    selection: Mapped[str] = mapped_column(String(255), nullable=False)
    odds: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=4), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(100), nullable=False)

    event_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    is_combined: Mapped[bool] = mapped_column(default=False, nullable=False)
    parent_prediction_id: Mapped[int | None] = mapped_column(
        ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    combined_legs: Mapped[int | None] = mapped_column(nullable=True)
    combined_odds: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )

    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[PredictionStatus] = mapped_column(
        Enum(PredictionStatus), default=PredictionStatus.PENDING, nullable=False
    )
    units_staked: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2), default=Decimal("1.00"), nullable=False
    )
    units_returned: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped["Prediction | None"] = relationship(
        "Prediction", remote_side="Prediction.id", back_populates="children", lazy="selectin"
    )
    children: Mapped[list["Prediction"]] = relationship(
        "Prediction", back_populates="parent", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Prediction(id={self.id}, {self.home_team} vs {self.away_team}, {self.selection} @ {self.odds}, {self.status})>"