from aiogram.fsm.state import State, StatesGroup

class ProductWizard(StatesGroup):
    # ۱. ساخت اولیه محصول
    waiting_for_name = State()
    
    # ۲. وضعیت‌های بخش قیمت و موجودی
    waiting_for_price = State()
    waiting_for_stock = State()
    
    # ۳. وضعیت‌های بخش توضیحات
    waiting_for_short_desc = State()
    waiting_for_long_desc = State()
    
    # ۴. وضعیت بخش تصویر
    waiting_for_image = State()
    
    # ۵. وضعیت‌های بخش سئو (Rank Math)
    waiting_for_seo_keyword = State()
    waiting_for_seo_title = State()
    waiting_for_seo_desc = State()
