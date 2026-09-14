import aiohttp
import base64
from config import WC_URL, WP_USER, WP_APP_PASS

class WordPressService:
    # متغیر کلاس برای نگهداری نشست اشتراکی
    _session = None

    def __init__(self):
        # مسیر اصلی API هسته وردپرس
        self.base_url = f"{WC_URL}/wp-json/wp/v2"
        
        # ساخت هدر احراز هویت با رمز عبور کاربردی (Application Password)
        credentials = f"{WP_USER}:{WP_APP_PASS}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        self.headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json"
        }

    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ==================================
    # متد ارسال مقاله (وبلاگ)
    # ==================================
    async def create_post(self, data: dict):
        url = f"{self.base_url}/posts"
        session = await self.get_session()
        async with session.post(url, json=data) as response:
            if response.status not in [200, 201]:
                text = await response.text()
                raise Exception(f"WP API Error {response.status}: {text}")
            return await response.json()

    # ==================================
    # متد آپدیت مقاله (برای اتصال تصویر شاخص)
    # ==================================
    async def update_post(self, post_id: int, data: dict):
        url = f"{self.base_url}/posts/{post_id}"
        session = await self.get_session()
        async with session.post(url, json=data) as response:
            if response.status not in [200, 201]:
                text = await response.text()
                raise Exception(f"WP API Error {response.status}: {text}")
            return await response.json()

    # ==================================
    # متد آپلود تصویر به همراه Alt و Title
    # ==================================
    async def upload_media(self, image_bytes: bytes, filename: str, alt_text: str, title: str):
        url = f"{self.base_url}/media"
        
        # تشخیص فرمت برای هدر
        content_type = "image/jpeg"
        if filename.lower().endswith(".webp"):
            content_type = "image/webp"
        elif filename.lower().endswith(".png"):
            content_type = "image/png"
            
        headers = {
            "Authorization": self.headers["Authorization"],
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type
        }
        
        session = await self.get_session()
        # ۱. آپلود فایل فیزیکی
        async with session.post(url, data=image_bytes, headers=headers) as response:
            if response.status not in [200, 201]:
                text = await response.text()
                raise Exception(f"WP Media API Error {response.status}: {text}")
            
            media_data = await response.json()
            media_id = media_data['id']
            
            # ۲. ثبت Alt Text و Title برای عکس آپلود شده
            update_url = f"{self.base_url}/media/{media_id}"
            update_payload = {
                "alt_text": alt_text,
                "title": title
            }
            async with session.post(update_url, json=update_payload, headers=self.headers):
                pass # خطاهای جزئی متا را نادیده می‌گیریم
                
            return media_id

    # ==================================
    # متد دریافت لیست آخرین مقالات (برای ویرایش)
    # ==================================
    async def get_recent_posts(self, per_page=10):
        url = f"{self.base_url}/posts"
        # status=any و context=edit تا پیش‌نویس‌ها هم با همین Application Password دیده شوند
        params = {"per_page": per_page, "orderby": "date", "order": "desc", "status": "any", "context": "edit"}
        session = await self.get_session()
        async with session.get(url, params=params) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"WP API Error {response.status}: {text}")
            return await response.json()

    # ==================================
    # متد دریافت یک مقاله (برای بارگذاری در ویرایش)
    # ==================================
    async def get_post(self, post_id: int):
        url = f"{self.base_url}/posts/{post_id}"
        session = await self.get_session()
        async with session.get(url, params={"context": "edit"}) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"WP API Error {response.status}: {text}")
            return await response.json()

    # ==================================
    # متد دریافت دسته‌بندی‌های وبلاگ (اختیاری برای آینده)
    # ==================================
    async def get_categories(self):
        url = f"{self.base_url}/categories"
        params = {"per_page": 100, "hide_empty": "0"}
        session = await self.get_session()
        async with session.get(url, params=params) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"WP API Error {response.status}: {text}")
            return await response.json()

# نمونه‌سازی یکتا (Singleton)
wp_service_instance = WordPressService()
