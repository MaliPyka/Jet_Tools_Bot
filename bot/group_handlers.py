from aiogram import Router, Bot, F
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.types import Message, ReactionTypeEmoji

from core.scooter_parser import parse_scooter_report, LINE_RE, get_text
from core.report_text import build_scooter_reply
from db.requests import get_or_create_user, get_active_shift, add_touches

group_router = Router()
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))


async def dm(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except TelegramForbiddenError:
        pass


async def process_list(message: Message, bot: Bot, text: str) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return

    user, created = await get_or_create_user(message.from_user.id)

    if created or not user.name:
        await dm(
            bot, message.from_user.id,
            "⚠️ Твоего профиля нет в базе (или данные были сброшены).\n\n"
            "Перейди в диалог со мной и напиши своё имя, чтобы отчёты из группы засчитывались!"
        )
        return

    old, new, unknown = parse_scooter_report(text)
    if old == 0 and new == 0:
        return

    active = await get_active_shift(user.id)
    if not active:
        await dm(
            bot, user.tg_id,
            "Ты забыл начать смену. "
            "Нажми «🟢 Начать смену» и отправь список ещё раз.",
        )
        return

    await add_touches(active.id, old, new)
    updated = await get_active_shift(user.id)

    await dm(bot, user.tg_id, build_scooter_reply(old, new, updated, unknown))



def has_scooter_lines(message: Message) -> bool:
    return bool(LINE_RE.search(get_text(message)))


def is_txt_document(message: Message) -> bool:
    if not message.document:
        return False
    return (message.document.file_name or "").lower().endswith(".txt")


@group_router.message(has_scooter_lines)
async def group_text_handler(message: Message, bot: Bot):
    await process_list(message, bot, get_text(message))


@group_router.message(is_txt_document)
async def group_file_handler(message: Message, bot: Bot):
    file = await bot.get_file(message.document.file_id)
    data = await bot.download_file(file.file_path)
    await process_list(message, bot, data.read().decode("utf-8"))