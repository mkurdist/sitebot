from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from config import ADMIN_ID

class AdminOnlyMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = getattr(event, "from_user", None)
        
        # اگر کاربر وجود نداشت یا آیدی او با ادمین یکی نبود، پیام را کاملاً نادیده بگیر
        if user is None or user.id != ADMIN_ID:
            return 
            
        return await handler(event, data)
