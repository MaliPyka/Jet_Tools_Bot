from datetime import timedelta
from db.models import Shift
from core.earnings import calculate_touches, calculate_earnings
from core.pluralize import pluralize
from core.timeutils import to_local


def fmt_num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def build_report_text(shift: Shift, user_name: str, final: bool = False) -> str:
    lines = [
        f"Смена {to_local(shift.created_at).strftime('%d.%m')}",
        user_name or "Скаут",
        f"Зона {shift.zone}",
        f"🔀: {shift.old_count}",
        f"🆕🔀: {shift.new_count}",
    ]

    if shift.corrections_count:
        lines.append(f"🅿️: {shift.corrections_count}")
    if shift.far_count:
        lines.append(f"Дальние: {shift.far_count} (+{shift.far_count * 5})")
    if shift.battery_count:
        lines.append(f"🔋: {shift.battery_count} ({shift.battery_count * 1.5:g})")

    touches = calculate_touches(
        shift.old_count, shift.new_count, shift.corrections_count,
        shift.far_count, shift.battery_count,
    )

    touches_text = round(touches) if final else fmt_num(touches)
    lines.append(f"Касаний: {touches_text}")

    return "\n".join(str(line) for line in lines if line is not None)


def build_scooter_reply(old: int, new: int, updated_shift: Shift, unknown: list[str]) -> str:
    touches = calculate_touches(updated_shift.old_count, updated_shift.new_count, 0, 0, 0)

    old_word = pluralize(old, "старый", "старых", "старых")
    new_word = pluralize(new, "новый", "новых", "новых")
    touches_word = pluralize(touches, "касание", "касания", "касаний")

    reply = (
        f"✅ <b>+{old}</b> {old_word}, <b>+{new}</b> {new_word}\n\n"
        f"📊 <b>Всего за смену</b>\n"
        f"🔀 Старых: {updated_shift.old_count}\n"
        f"🆕 Новых: {updated_shift.new_count}\n"
        f"⚡ {fmt_num(touches)} {touches_word}"
    )

    if unknown:
        reply += f"\n\n⚠️ Не распознал модель ({len(unknown)} шт.): {', '.join(unknown)}"

    return reply


def build_period_text(start, end, shifts) -> str:
    title = f"{start:%d.%m}–{(end - timedelta(days=1)):%d.%m}"
    if not shifts:
        return f"📅 <b>{title}</b>\nЗакрытых смен пока нет."

    lines = []
    for s in shifts:
        earn = s.earnings or 0
        date = f"{to_local(s.created_at):%d.%m}"
        if s.kind == "charger":
            lines.append(f"{date} · 🔋{s.battery_count} · {earn} лари")
        else:
            t = calculate_touches(s.old_count, s.new_count, s.corrections_count, s.far_count, s.battery_count)
            lines.append(f"{date} · ⚡{fmt_num(t)} · {earn} лари")

    total_money = sum(s.earnings or 0 for s in shifts)
    return (
        f"📅 <b>{title}</b>\n"
        f"Смен: {len(shifts)}\n"
        f"💰 <b>{total_money} лари</b>\n\n"
        + "\n".join(lines)
    )