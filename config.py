import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# کلیدهای ووکامرس
WC_URL = os.getenv("WC_URL")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")
WC_WEBHOOK_SECRET = os.getenv("WC_WEBHOOK_SECRET")  # <--- کلید امنیتی وب‌هوک اضافه شد

# بررسی وجود متغیرها (وب‌هوک سکرت هم به بررسی اضافه شد)
if not all([BOT_TOKEN, ADMIN_ID, WC_URL, WC_CONSUMER_KEY, WC_CONSUMER_SECRET, WC_WEBHOOK_SECRET]):
    raise ValueError("❌ Missing environment variables! Check Render settings.")

ADMIN_ID = int(ADMIN_ID)
# حذف اسلش اضافی از انتهای آدرس سایت در صورت وجود
WC_URL = WC_URL.rstrip("/")
