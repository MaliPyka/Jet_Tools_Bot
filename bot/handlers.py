from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from core.timeutils import TBILISI, period_dates, to_db_bounds
from core.report_text import build_period_text, build_report_text, build_scooter_reply
from core.scooter_parser import parse_scooter_report, LINE_RE, get_text
from core.earnings import calculate_touches
from bot.middlewares import NameRequiredMiddleware


from db.requests import (
    get_or_create_user,
    set_user_name,
    get_user_by_id,
    get_user,
    start_shift,
    get_active_shift,
    get_shift,
    add_touches,
    set_zone,
    set_corrections,
    add_far,
    add_battery,
    finalize_shift,
    get_period_shifts,
    add_charger_shift,
    add_scout_shift,
    set_worker_type,
)
from bot.keyboard import (
    main_kb,
    zones_kb,
    final_report_kb,
    corrections_kb,
    salary_kb,
    worker_type_kb,
    history_choice_kb,
)
from bot.states import StartStates, ReportStates, ChargerStates, ScoutStates

router = Router()
router.message.filter(F.chat.type == "private")

router.message.middleware(NameRequiredMiddleware())
router.callback_query.middleware(NameRequiredMiddleware())


def report_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Добавить дальние", callback_data="add_far"),
            InlineKeyboardButton(text="🔋 Добавить АКБ", callback_data="add_battery"),
        ],
        [InlineKeyboardButton(text="✅ Завершить смену", callback_data="finish_shift")],
    ])


# ---------- Старт и регистрация ----------

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await message.answer(f"С возвращением, {user.name}!", reply_markup=main_kb)


BUTTON_TEXTS = {"🟢 Начать смену", "📋 Составить отчёт", "💰 Зп"}  # тексты своих кнопок


@router.message(StartStates.waiting_name)
async def save_name_handler(message: Message, state: FSMContext):
    name = (message.text or "").strip()

    if not name or len(name) > 40 or name.startswith("/") or name in BUTTON_TEXTS:
        await message.answer("Напиши своё имя текстом, например: Имя Фамилия")
        return

    await set_user_name(message.from_user.id, name)
    await state.clear()
    await message.answer("Теперь можешь начинать смену.", reply_markup=main_kb)


@router.callback_query(StartStates.waiting_history_choice, F.data.startswith("history:"))
async def history_choice_handler(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    await state.clear()
    
    if choice == "yes":
        await callback.message.edit_text(
            "Отлично! Добавить прошедшие смены можно в разделе **«💰 Зп»** через кнопки внизу."
        )
    else:
        await callback.message.edit_text("Хорошо, начнем с чистого листа!")

    await callback.message.answer("Главное меню:", reply_markup=main_kb)
    await callback.answer()


# ---------- Смена ----------

@router.message(F.text == "🟢 Начать смену")
async def start_shift_handler(message: Message):
    user, _ = await get_or_create_user(message.from_user.id)

    active = await get_active_shift(user.id)
    if active:
        await message.answer("У тебя уже есть активная смена")
        return

    await start_shift(user.id)
    await message.answer("Смена начата")


# ---------- Парсинг списков самокатов ----------

def is_scooter_report(message: Message) -> bool:
    return bool(LINE_RE.search(get_text(message)))


@router.message(is_scooter_report)
async def scooter_report_handler(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)

    active = await get_active_shift(user.id)
    if not active:
        await message.answer("Нет активной смены. Сначала начни смену")
        return

    old, new, unknown = parse_scooter_report(message)

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
async def scooter_report_file_handler(message: Message, bot: Bot, state: FSMContext):

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


# ---------- Составление отчёта ----------

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
    user_name = user.name if user and user.name else "Скаут"

    await bot.edit_message_text(
        text=build_report_text(shift, user_name),
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
    await message.delete()


async def delete_quietly(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "add_far")
async def add_far_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйся (/start)")
        return

    active = await get_active_shift(user.id)
    if not active:
        await callback.answer("Смена уже завершена или не начата")
        return

    prompt = await callback.message.answer("Сколько дальних самокатов?")
    await state.update_data(
        shift_id=active.id,
        report_chat_id=callback.message.chat.id,
        report_message_id=callback.message.message_id,
        prompt_id=prompt.message_id,
    )
    await state.set_state(ReportStates.waiting_far)
    await callback.answer()


@router.message(ReportStates.waiting_far)
async def add_far_finish(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit():
        await message.answer("Нужно число, попробуй ещё раз")
        return

    data = await state.get_data()
    shift_id = data["shift_id"]

    await add_far(shift_id, int(message.text))
    await state.clear()

    shift = await get_shift(shift_id)
    user = await get_user_by_id(shift.user_id)
    user_name = user.name if user and user.name else "Скаут"
    text = build_report_text(shift, user_name)

    try:
        await bot.edit_message_text(
            text=text,
            chat_id=data["report_chat_id"],
            message_id=data["report_message_id"],
            reply_markup=report_kb(),
        )
    except TelegramBadRequest:
        pass  # отчёт не изменился

    await delete_quietly(bot, message.chat.id, data.get("prompt_id"))  # вопрос бота
    await delete_quietly(bot, message.chat.id, message.message_id)     # ответ пользователя


@router.callback_query(F.data == "add_battery")
async def add_battery_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйся (/start)")
        return

    active = await get_active_shift(user.id)
    if not active:
        await callback.answer("Смена уже завершена или не начата.")
        return

    prompt = await callback.message.answer("Сколько замен АКБ?")
    await state.update_data(
        shift_id=active.id,
        report_chat_id=callback.message.chat.id,
        report_message_id=callback.message.message_id,
        prompt_id=prompt.message_id,
    )
    await state.set_state(ReportStates.waiting_battery)
    await callback.answer()


@router.message(ReportStates.waiting_battery)
async def add_battery_finish(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit():
        await message.answer("Нужно число, попробуй ещё раз")
        return

    data = await state.get_data()
    shift_id = data["shift_id"]

    await add_battery(shift_id, int(message.text))
    await state.clear()

    shift = await get_shift(shift_id)
    user = await get_user_by_id(shift.user_id)
    user_name = user.name if user and user.name else "Скаут"
    text = build_report_text(shift, user_name)

    try:
        await bot.edit_message_text(
            text=text,
            chat_id=data["report_chat_id"],
            message_id=data["report_message_id"],
            reply_markup=report_kb(),
        )
    except TelegramBadRequest:
        pass  # отчёт не изменился

    await delete_quietly(bot, message.chat.id, data.get("prompt_id"))
    await delete_quietly(bot, message.chat.id, message.message_id)     


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


# ---------- Ручное добавление прошлых смен (Скаут и Чарджер) ----------

# --- Скаут ---

@router.callback_query(F.data == "add_scout_manual")
async def add_scout_start(callback: CallbackQuery, state: FSMContext):
    prompt = await callback.message.answer("За какое число смена? (например: 12.10 или 14,10)")
    await state.set_state(ScoutStates.waiting_date)
    await state.update_data(
        salary_chat_id=callback.message.chat.id,
        salary_msg_id=callback.message.message_id,
        prompt_id=prompt.message_id,
    )
    await callback.answer()


@router.message(ScoutStates.waiting_date)
async def add_scout_date(message: Message, state: FSMContext, bot: Bot):
    date_text = message.text.strip()
    data = await state.get_data()

    if "prompt_id" in data:
        try:
            await bot.delete_message(message.chat.id, data["prompt_id"])
        except Exception:
            pass

    prompt2 = await message.answer(f"Принято ({date_text}). Сколько касаний было за смену? (можно дробное, например: 158.5 или 158,5)")
    
    await state.update_data(
        shift_date=date_text,
        prompt_id=prompt2.message_id,
    )
    await state.set_state(ScoutStates.waiting_touches)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(ScoutStates.waiting_touches)
async def add_scout_finish(message: Message, state: FSMContext, bot: Bot):
    raw_text = message.text.strip().replace(",", ".")
    
    try:
        touches = float(raw_text)
        if touches <= 0:
            raise ValueError
    except ValueError:
        err = await message.answer("Нужно число больше нуля, попробуй ещё раз.")
        try:
            await message.delete()
        except Exception:
            pass
        return

    data = await state.get_data()
    await state.clear()

    shift_date = data.get("shift_date")

    # Используем твою функцию get_user из database/requests
    user = await get_user(message.from_user.id)
    if not user:
        return

    await add_scout_shift(user.id, touches=touches, date_str=shift_date)

    try:
        await bot.edit_message_text(
            text=await render_salary(user.id),
            chat_id=data["salary_chat_id"],
            message_id=data["salary_msg_id"],
            reply_markup=salary_kb(),
        )
    except Exception:
        pass

    if "prompt_id" in data:
        try:
            await bot.delete_message(message.chat.id, data["prompt_id"])
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass


# --- Чарджер ---

@router.callback_query(F.data == "add_charger")
async def add_charger_start(callback: CallbackQuery, state: FSMContext):
    prompt = await callback.message.answer("За какое число смена? (например: 12.10 или 14,10)")
    await state.set_state(ChargerStates.waiting_date)
    await state.update_data(
        salary_chat_id=callback.message.chat.id,
        salary_msg_id=callback.message.message_id,
        prompt_id=prompt.message_id,
    )
    await callback.answer()


@router.message(ChargerStates.waiting_date)
async def add_charger_date(message: Message, state: FSMContext, bot: Bot):
    date_text = message.text.strip()
    data = await state.get_data()

    if "prompt_id" in data:
        try:
            await bot.delete_message(message.chat.id, data["prompt_id"])
        except Exception:
            pass

    prompt2 = await message.answer(f"Принято ({date_text}). Сколько замен АКБ было за смену? (число)")
    
    await state.update_data(
        shift_date=date_text,
        prompt_id=prompt2.message_id,
    )
    await state.set_state(ChargerStates.waiting_swaps)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(ChargerStates.waiting_swaps)
async def add_charger_finish(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit() or int(message.text) == 0:
        await message.answer("Нужно целое число больше нуля, попробуй ещё раз.")
        try:
            await message.delete()
        except Exception:
            pass
        return

    data = await state.get_data()
    await state.clear()

    shift_date = data.get("shift_date")
    swaps = int(message.text)


    user = await get_user(message.from_user.id)
    if not user:
        return

    await add_charger_shift(user.id, count=swaps, date_str=shift_date)

    try:
        await bot.edit_message_text(
            text=await render_salary(user.id),
            chat_id=data["salary_chat_id"],
            message_id=data["salary_msg_id"],
            reply_markup=salary_kb(),
        )
    except Exception:
        pass

    if "prompt_id" in data:
        try:
            await bot.delete_message(message.chat.id, data["prompt_id"])
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass