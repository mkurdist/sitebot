from aiogram.fsm.state import State, StatesGroup

class ProductWizard(StatesGroup):
    waiting_for_name = State()
    
    waiting_for_price = State()
    waiting_for_stock = State()
    
    waiting_for_short_desc = State()
    waiting_for_long_desc = State()
    
    # وضعیت‌های جدید برای بخش تصویر پیشرفته
    waiting_for_image = State()
    waiting_for_image_alt = State()
    waiting_for_image_title = State()
    
    waiting_for_seo_keyword = State()
    waiting_for_seo_title = State()
    waiting_for_seo_desc = State()
