import re
from datetime import datetime
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from db.models import User, Shift
from db.base import async_session
from core.earnings import calculate_earnings, calculate_touches, calculate_charger_earnings
from core.timeutils import TBILISI


async def set_user_name(tg_id: int, name: str) -> None:
    async with async_session() as session:
        await session.execute(
            update(User).where(User.tg_id == tg_id).values(name=name)
        )
        await session.commit()


async def set_zone(shift_id: int, zone: str) -> None:
    async with async_session() as session:
        await session.execute(
            update(Shift).where(Shift.id == shift_id).values(zone=zone)
        )
        await session.commit()


async def get_user_by_id(user_id: int) -> User:
    async with async_session() as session:
        return await session.get(User, user_id)


async def get_user(tg_id: int) -> User | None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        return result.scalar_one_or_none()


async def add_user(tg_id: int) -> User:
    async with async_session() as session:
        user = User(tg_id=tg_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_or_create_user(tg_id: int) -> tuple[User, bool]:
    user = await get_user(tg_id)
    if user:
        return user, False

    async with async_session() as session:
        user = User(tg_id=tg_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, True


async def start_shift(user_id: int) -> Shift:
    async with async_session() as session:
        user = await session.get(User, user_id)
        shift = Shift(user_id=user_id, worker_type=user.worker_type or "night")
        session.add(shift)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return await get_active_shift(user_id)
        await session.refresh(shift)
        return shift


async def set_worker_type(user_id: int, worker_type: str) -> None:
    async with async_session() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(worker_type=worker_type)
        )
        await session.execute(
            update(Shift)
            .where(Shift.user_id == user_id, Shift.ended_at.is_(None))
            .values(worker_type=worker_type)
        )
        await session.commit()


async def get_active_shift(user_id: int) -> Shift | None:
    async with async_session() as session:
        result = await session.execute(
            select(Shift)
            .where(Shift.user_id == user_id, Shift.ended_at.is_(None))
            .order_by(Shift.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()


async def add_touches(shift_id: int, old: int, new: int) -> None:
    async with async_session() as session:
        await session.execute(
            update(Shift)
            .where(Shift.id == shift_id)
            .values(old_count=Shift.old_count + old, new_count=Shift.new_count + new)
        )
        await session.commit()


async def end_shift(shift_id: int) -> Shift:
    async with async_session() as session:
        shift = await session.get(Shift, shift_id)

        weighted_score = shift.old_count * 1 + shift.new_count * 1.25
        shift.earnings = calculate_earnings(weighted_score)
        shift.ended_at = func.now()

        await session.commit()
        await session.refresh(shift)
        return shift


async def get_shift(shift_id: int) -> Shift:
    async with async_session() as session:
        return await session.get(Shift, shift_id)


async def set_corrections(shift_id: int, count: int) -> None:
    async with async_session() as session:
        await session.execute(
            update(Shift).where(Shift.id == shift_id).values(corrections_count=count)
        )
        await session.commit()


async def add_far(shift_id: int, count: int) -> None:
    async with async_session() as session:
        await session.execute(
            update(Shift).where(Shift.id == shift_id).values(far_count=Shift.far_count + count)
        )
        await session.commit()


async def add_battery(shift_id: int, count: int) -> None:
    async with async_session() as session:
        await session.execute(
            update(Shift).where(Shift.id == shift_id).values(battery_count=Shift.battery_count + count)
        )
        await session.commit()


async def finalize_shift(shift_id: int) -> Shift:
    async with async_session() as session:
        shift = await session.get(Shift, shift_id)
        touches = calculate_touches(
            shift.old_count, shift.new_count, shift.corrections_count,
            shift.far_count, shift.battery_count,
        )
        shift.earnings = calculate_earnings(touches, shift.worker_type)
        shift.ended_at = func.now()
        await session.commit()
        await session.refresh(shift)
        return shift


async def get_period_shifts(user_id: int, start: datetime, end: datetime) -> list[Shift]:
    async with async_session() as session:
        result = await session.execute(
            select(Shift)
            .where(
                Shift.user_id == user_id,
                Shift.ended_at.is_not(None),
                Shift.created_at >= start,
                Shift.created_at < end,
            )
            .order_by(Shift.created_at)
        )
        return list(result.scalars().all())


# ---------- РУЧНОЕ ДОБАВЛЕНИЕ СМЕН (ЗАДНИМ ЧИСЛОМ) ----------

def parse_custom_date(date_str: str | None) -> datetime:
    created_at = datetime.now(TBILISI).replace(tzinfo=None)
    if date_str:
        clean_date = re.sub(r'[,/]', '.', date_str.strip())
        try:
            day, month = map(int, clean_date.split("."))
            created_at = created_at.replace(month=month, day=day)
        except ValueError:
            pass
    return created_at


async def add_scout_shift(user_id: int, touches: float, date_str: str = None) -> Shift:
    async with async_session() as session:
        user = await session.get(User, user_id)
        worker_type = user.worker_type if user and user.worker_type else "night"
        
        created_at = parse_custom_date(date_str)
        earnings = calculate_earnings(touches, worker_type)

        shift = Shift(
            user_id=user_id,
            kind="scout",
            old_count=touches,  # Сохраняем точное число касаний (float)
            created_at=created_at,
            ended_at=created_at,
            earnings=earnings,
            worker_type=worker_type,
        )
        session.add(shift)
        await session.commit()
        await session.refresh(shift)
        return shift


async def add_charger_shift(user_id: int, count: int, date_str: str = None) -> Shift:
    async with async_session() as session:
        created_at = parse_custom_date(date_str)
        earnings = calculate_charger_earnings(count)

        shift = Shift(
            user_id=user_id,
            kind="charger",
            battery_count=count,
            created_at=created_at,
            ended_at=created_at,
            earnings=earnings,
        )
        session.add(shift)
        await session.commit()
        await session.refresh(shift)
        return shift