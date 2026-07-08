from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create_from_telegram(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None,
        is_bot: bool = False,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            is_bot=is_bot,
            balance=Decimal("0.00"),
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_or_create(self, telegram_id: int, **kwargs) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = await self.create_from_telegram(telegram_id, **kwargs)
        return user

    async def update_balance(self, user_id: int, amount: Decimal) -> User:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"Usuario {user_id} no encontrado")
        user.balance += amount
        await self.session.flush()
        return user