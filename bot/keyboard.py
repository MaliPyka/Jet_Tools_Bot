from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton


ZONES = ["Сабуртало", "Ваке", "Руставели", "Марджанишвили"]


main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🟢 Начать смену")],
        [KeyboardButton(text="📋 Составить отчёт")],
        [KeyboardButton(text="💰 Зп")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие",
)


def final_report_kb(report_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать отчёт", copy_text=CopyTextButton(text=report_text))],
    ])


def zones_kb() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=zone, callback_data=f"zone:{zone}")] for zone in ZONES]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def corrections_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{n}\ufe0f\u20e3", callback_data=f"corr:{n}") for n in range(1, 6)],
        [InlineKeyboardButton(text="Нет поправок", callback_data="corr:0")],
    ])


def salary_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔋 Добавить смену чарджера", callback_data="add_charger")],
    ])


def worker_type_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌙 Ночной", callback_data=f"{prefix}:night"),
        InlineKeyboardButton(text="☀️ Дневной", callback_data=f"{prefix}:day"),
    ]])