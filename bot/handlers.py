from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router, F, Bot
from datetime import datetime, timedelta
from core.timeutils import TBILISI, period_dates, to_db_bounds
from core.report_text import build_period_text
from db.requests import get_period_shifts, add_charger_shift, set_worker_type

from db.requests import (
    get_or_create_user,
    set_user_name,
    get_user_by_id,
    start_shift,
    get_active_shift,
    get_shift,
    add_touches,
    set_zone,
    set_corrections,
    add_far,
    add_battery,
    finalize_shift,
)
from bot.keyboard import main_kb, zones_kb, final_report_kb, corrections_kb, salary_kb, worker_type_kb
from bot.states import StartStates, ReportStates, ChargerStates
from core.scooter_parser import parse_scooter_report, LINE_RE
from core.report_text import build_report_text, build_scooter_reply
from core.earnings import calculate_touches

router = Router()
router.message.filter(F.chat.type == "private")


def report_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Добавить дальние", callback_data="add_far"),
            InlineKeyboardButton(text="🔋 Добавить АКБ", callback_data="add_battery"),
        ],
        [InlineKeyboardButton(text="✅ Завершить смену", callback_data="finish_shift")],
    ])


# ---------- старт ----------

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    user, created = await get_or_create_user(message.from_user.id)

    if created or not user.name:
        await state.set_state(StartStates.waiting_name)
        await message.answer("Напиши своё имя (оно будет в отчётах)")
        return

    await message.answer(f"С возвращением", reply_markup=main_kb)


@router.message(StartStates.waiting_name)
async def save_name_handler(message: Message, state: FSMContext):
    await set_user_name(message.from_user.id, message.text.strip())
    await state.clear()
    await message.answer(f"Чтобы бот начал считать касания - начни смену", reply_markup=main_kb)


# ---------- смена ----------

@router.message(F.text == "🟢 Начать смену")
async def start_shift_handler(message: Message):
    user, _ = await get_or_create_user(message.from_user.id)

    active = await get_active_shift(user.id)
    if active:
        await message.answer("У тебя уже есть активная смена")
        return

    await start_shift(user.id)
    await message.answer("Смена начата")


# ---------- парсинг списков самокатов ----------

def is_scooter_report(message: Message) -> bool:
    return bool(message.text) and bool(LINE_RE.search(message.text))


@router.message(is_scooter_report)
async def scooter_report_handler(message: Message):
    user, _ = await get_or_create_user(message.from_user.id)

    active = await get_active_shift(user.id)
    if not active:
        await message.answer("Нет активной смены. Сначала начни смену")
        return

    old, new, unknown = parse_scooter_report(message.text)

    if old == 0 and new == 0:
        await message.answer("Не нашёл ни одного самоката в сообщении")
        return

    await add_touches(active.id, old, new)
    updated = await get_active_shift(user.id)

    await message.answer(build_scooter_reply(old, new, updated, unknown))


def is_txt_document(message: Message) -> bool:
    if not message.document:
        return False
    file_name = message.document.file_name or ""
    return file_name.lower().endswith(".txt")


@router.message(is_txt_document)
async def scooter_report_file_handler(message: Message, bot: Bot):
    user, _ = await get_or_create_user(message.from_user.id)

    active = await get_active_shift(user.id)
    if not active:
        await message.answer("Нет активной смены. Сначала начни смену")
        return

    file = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file.file_path)
    text = file_bytes.read().decode("utf-8")

    old, new, unknown = parse_scooter_report(text)

    if old == 0 and new == 0:
        await message.answer("Не нашёл ни одного самоката в файле")
        return

    await add_touches(active.id, old, new)
    updated = await get_active_shift(user.id)

    await message.answer(build_scooter_reply(old, new, updated, unknown))


# ---------- составление отчёта ----------

@router.message(F.text == "📋 Составить отчёт")
async def compose_report_start(message: Message, state: FSMContext):
    user, _ = await get_or_create_user(message.from_user.id)
    active = await get_active_shift(user.id)

    if not active:
        await message.answer("Сначала начни смену")
        return

    await state.update_data(shift_id=active.id)
    await state.set_state(ReportStates.waiting_zone)
    await message.answer("Выбери зону:", reply_markup=zones_kb())


@router.callback_query(ReportStates.waiting_zone, F.data.startswith("zone:"))
async def compose_report_zone(callback: CallbackQuery, state: FSMContext):
    zone = callback.data.split(":", 1)[1]
    data = await state.get_data()

    await set_zone(data["shift_id"], zone)
    await state.update_data(
        corr_chat_id=callback.message.chat.id,
        corr_msg_id=callback.message.message_id,
    )
    await state.set_state(ReportStates.waiting_corrections)

    await callback.message.edit_text("Касания за поправки:", reply_markup=corrections_kb())
    await callback.answer()


async def finish_corrections(bot: Bot, state: FSMContext, count: int) -> None:
    data = await state.get_data()
    shift_id = data["shift_id"]

    await set_corrections(shift_id, count)
    await state.clear()

    shift = await get_shift(shift_id)
    user = await get_user_by_id(shift.user_id)
    await bot.edit_message_text(
        text=build_report_text(shift, user.name),
        chat_id=data["corr_chat_id"],
        message_id=data["corr_msg_id"],
        reply_markup=report_kb(),
    )


@router.callback_query(ReportStates.waiting_corrections, F.data.startswith("corr:"))
async def corrections_button(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await finish_corrections(bot, state, int(callback.data.split(":", 1)[1]))
    await callback.answer()


@router.message(ReportStates.waiting_corrections)
async def corrections_text(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit():
        await message.answer("Нужно число, попробуй ещё раз.")
        return

    await finish_corrections(bot, state, int(message.text))
    await message.delete()  # убираем введённое число, чтобы не засорять чат


@router.callback_query(F.data == "add_far")
async def add_far_start(callback: CallbackQuery, state: FSMContext):
    user, _ = await get_or_create_user(callback.from_user.id)
    active = await get_active_shift(user.id)

    if not active:
        await callback.answer("Смена уже завершена")
        return

    await state.update_data(
        shift_id=active.id,
        report_chat_id=callback.message.chat.id,
        report_message_id=callback.message.message_id,
    )
    await state.set_state(ReportStates.waiting_far)
    await callback.message.answer("Сколько дальних самокатов?")
    await callback.answer()


@router.message(ReportStates.waiting_far)
async def add_far_finish(message: Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        await message.answer("Нужно число, попробуй ещё раз")
        return

    data = await state.get_data()
    shift_id = data["shift_id"]

    await add_far(shift_id, int(message.text))
    await state.clear()

    shift = await get_shift(shift_id)
    user = await get_user_by_id(shift.user_id)
    text = build_report_text(shift, user.name)

    await bot.edit_message_text(
        text=text,
        chat_id=data["report_chat_id"],
        message_id=data["report_message_id"],
        reply_markup=report_kb(),
    )
    await message.delete()


@router.callback_query(F.data == "add_battery")
async def add_battery_start(callback: CallbackQuery, state: FSMContext):
    user, _ = await get_or_create_user(callback.from_user.id)
    active = await get_active_shift(user.id)

    if not active:
        await callback.answer("Смена уже завершена.")
        return

    await state.update_data(
        shift_id=active.id,
        report_chat_id=callback.message.chat.id,
        report_message_id=callback.message.message_id,
    )
    await state.set_state(ReportStates.waiting_battery)
    await callback.message.answer("Сколько замен АКБ?")
    await callback.answer()


@router.message(ReportStates.waiting_battery)
async def add_battery_finish(message: Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        await message.answer("Нужно число, попробуй ещё раз")
        return

    data = await state.get_data()
    shift_id = data["shift_id"]

    await add_battery(shift_id, int(message.text))
    await state.clear()

    shift = await get_shift(shift_id)
    user = await get_user_by_id(shift.user_id)
    text = build_report_text(shift, user.name)

    await bot.edit_message_text(
        text=text,
        chat_id=data["report_chat_id"],
        message_id=data["report_message_id"],
        reply_markup=report_kb(),
    )
    await message.delete()

@router.callback_query(F.data == "finish_shift")
async def finish_shift_handler(callback: CallbackQuery):
    user, _ = await get_or_create_user(callback.from_user.id)
    active = await get_active_shift(user.id)

    if not active:
        await callback.answer("Смена уже завершена")
        return


    shift = await finalize_shift(active.id)
    user_obj = await get_user_by_id(shift.user_id)
    final_text = build_report_text(shift, user_obj.name, final=True)

    await callback.message.edit_text(final_text, reply_markup=final_report_kb(final_text))
    await callback.answer()


async def render_salary(user_id: int) -> str:
    today = datetime.now(TBILISI).date()
    start, end = period_dates(today)
    shifts = await get_period_shifts(user_id, *to_db_bounds(start, end))
    return build_period_text(start, end, shifts)


WT_LABEL = {"night": "🌙 Ночной", "day": "☀️ Дневной"}


@router.message(F.text == "💰 Зп")
async def salary_handler(message: Message):
    user, _ = await get_or_create_user(message.from_user.id)

    if user.worker_type is None:
        await message.answer(
            "Ты работаешь в ночную или дневную смену?\n"
            "Потом это можно поменять командой /status",
            reply_markup=worker_type_kb("wt"),
        )
        return

    await message.answer(await render_salary(user.id), reply_markup=salary_kb())


@router.callback_query(F.data.startswith("wt:"))
async def worker_type_first(callback: CallbackQuery):
    user, _ = await get_or_create_user(callback.from_user.id)
    await set_worker_type(user.id, callback.data.split(":", 1)[1])
    await callback.message.edit_text(await render_salary(user.id), reply_markup=salary_kb())
    await callback.answer()


@router.message(Command("status"))
async def status_handler(message: Message):
    user, _ = await get_or_create_user(message.from_user.id)
    current = WT_LABEL.get(user.worker_type, "не выбран")
    await message.answer(f"Сейчас: {current}\nВыбери новый статус:", reply_markup=worker_type_kb("ws"))


@router.callback_query(F.data.startswith("ws:"))
async def worker_type_change(callback: CallbackQuery):
    user, _ = await get_or_create_user(callback.from_user.id)
    wt = callback.data.split(":", 1)[1]
    await set_worker_type(user.id, wt)
    await callback.message.edit_text(f"Готово: {WT_LABEL[wt]}. Действует для текущей и новых смен.")
    await callback.answer()


@router.callback_query(F.data == "add_charger")
async def add_charger_start(callback: CallbackQuery, state: FSMContext):
    prompt = await callback.message.answer("Сколько замен АКБ было за смену? (число)")
    await state.set_state(ChargerStates.waiting_swaps)
    await state.update_data(
        salary_chat_id=callback.message.chat.id,
        salary_msg_id=callback.message.message_id,
        prompt_id=prompt.message_id,
    )
    await callback.answer()


@router.message(ChargerStates.waiting_swaps)
async def add_charger_finish(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit() or int(message.text) == 0:
        await message.answer("Нужно число больше нуля, попробуй ещё раз.")
        return

    data = await state.get_data()
    await state.clear()

    user, _ = await get_or_create_user(message.from_user.id)
    await add_charger_shift(user.id, int(message.text))

    await bot.edit_message_text(
        text=await render_salary(user.id),
        chat_id=data["salary_chat_id"],
        message_id=data["salary_msg_id"],
        reply_markup=salary_kb(),
    )
    await bot.delete_message(message.chat.id, data["prompt_id"])
    await message.delete()