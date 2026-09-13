import os
from dotenv import load_dotenv

# این خط برای زمانی که روی سیستم لوکال هستید کاربرد دارد (از فایل .env می‌خواند)
# روی سرور ابری، متغیرها مستقیماً از تنظیمات سرور خوانده می‌شوند.
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# بررسی وجود متغیرهای حیاتی
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing in environment variables!")
if not ADMIN_ID:
    raise ValueError("❌ ADMIN_ID is missing in environment variables!")

# تبدیل آیدی ادمین به عدد صحیح
ADMIN_ID = int(ADMIN_ID)
