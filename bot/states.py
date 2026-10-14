from aiogram.fsm.state import State, StatesGroup


class StartStates(StatesGroup):
    waiting_name = State()
    waiting_history_choice = State()


class ScoutStates(StatesGroup):
    waiting_date = State()
    waiting_touches = State()


class ChargerStates(StatesGroup):
    waiting_date = State()
    waiting_swaps = State()


class ReportStates(StatesGroup):
    waiting_zone = State()
    waiting_corrections = State()
    waiting_far = State()
    waiting_battery = State()