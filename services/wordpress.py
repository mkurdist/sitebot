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
