import aiohttp
import base64
from config import WC_URL, WP_USER, WP_APP_PASS

class WordPressService:
    _session = None

    def __init__(self):
        self.base_url = f"{WC_URL}/wp-json/wp/v2"
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

    async def create_post(self, data: dict):
        url = f"{self.base_url}/posts"
        session = await self.get_session()
        async with session.post(url, json=data) as response:
            if response.status not in [200, 201]:
                text = await response.text()
                raise Exception(f"WP API Error {response.status}: {text}")
            return await response.json()

    # ==================================
    # متد جدید: آپدیت مقاله (برای اتصال عکس)
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
    # متد جدید: آپلود مستقیم مدیا به همراه Alt و Title
    # ==================================
    async def upload_media(self, image_bytes: bytes, filename: str, alt_text: str, title: str):
        url = f"{self.base_url}/media"
        
        # تشخیص خودکار فرمت برای هدر ارسال
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
        async with session.post(url, data=image_bytes, headers=headers) as response:
            if response.status not in [200, 201]:
                text = await response.text()
                raise Exception(f"WP Media API Error {response.status}: {text}")
            
            media_data = await response.json()
            media_id = media_data['id']
            
            # درخواست دوم برای ثبت Alt Text و Title تصویر در دیتابیس وردپرس
            update_url = f"{self.base_url}/media/{media_id}"
            update_payload = {
                "alt_text": alt_text,
                "title": title
            }
            async with session.post(update_url, json=update_payload, headers=self.headers):
                pass 
                
            return media_id

wp_service_instance = WordPressService()
