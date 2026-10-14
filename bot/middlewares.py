from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bot.states import StartStates
from db.requests import get_or_create_user


class NameRequiredMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        state = data["state"]

        if await state.get_state() == StartStates.waiting_name.state:
            return await handler(event, data)
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        user, _ = await get_or_create_user(event.from_user.id)
        if user.name:
            return await handler(event, data)

        await state.set_state(StartStates.waiting_name)
        message = event if isinstance(event, Message) else event.message
        await message.answer("Сначала представься: как тебя зовут? (это имя будет в отчётах)")
        if isinstance(event, CallbackQuery):
            await event.answer()