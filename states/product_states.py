from aiogram.fsm.state import State, StatesGroup

class ProductWizard(StatesGroup):
    name = State()
    short_description = State()
    price = State()
    stock = State()
