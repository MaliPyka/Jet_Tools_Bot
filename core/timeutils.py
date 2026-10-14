from datetime import date, datetime
from zoneinfo import ZoneInfo

TBILISI = ZoneInfo("Asia/Tbilisi")
UTC = ZoneInfo("UTC")


def to_local(dt: datetime) -> datetime:
    """Время из БД (naive UTC) -> время Тбилиси"""
    return dt.replace(tzinfo=UTC).astimezone(TBILISI)


def period_dates(day: date) -> tuple[date, date]:
    """Период, в который попадает день: 1-15 или 16-конец месяца.
    Возвращает (первый день периода, первый день следующего периода)."""
    if day.day <= 15:
        return date(day.year, day.month, 1), date(day.year, day.month, 16)
    if day.month == 12:
        return date(day.year, 12, 16), date(day.year + 1, 1, 1)
    return date(day.year, day.month, 16), date(day.year, day.month + 1, 1)


def to_db_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Границы периода по Тбилиси -> naive UTC для запроса к БД"""
    def conv(d: date) -> datetime:
        return datetime(d.year, d.month, d.day, tzinfo=TBILISI).astimezone(UTC).replace(tzinfo=None)
    return conv(start), conv(end)