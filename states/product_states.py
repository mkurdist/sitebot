from aiogram.fsm.state import State, StatesGroup

class ProductWizard(StatesGroup):
    # دریافت نام اولیه
    waiting_for_name = State()
    
    # وضعیت‌های مربوط به ویرایش از طریق داشبورد
    waiting_for_price_stock = State()
    waiting_for_seo = State()
    waiting_for_desc = State()
    # (بخش عکس و دسته‌بندی را در مراحل بعدی اضافه می‌کنیم)
