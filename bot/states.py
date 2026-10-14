from aiogram.fsm.state import State, StatesGroup


class StartStates(StatesGroup):
    waiting_name = State()


class ReportStates(StatesGroup):
    waiting_zone = State()
    waiting_corrections = State()
    waiting_far = State()
    waiting_battery = State()


class ChargerStates(StatesGroup):
    waiting_swaps = State()