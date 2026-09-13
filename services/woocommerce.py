import aiohttp
from config import WC_URL, WC_CONSUMER_KEY, WC_CONSUMER_SECRET

class WooCommerceService:
    def __init__(self):
        self.base_url = WC_URL
        # سیستم احراز هویت استاندارد ووکامرس
        self.auth = aiohttp.BasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)

    async def get_latest_products(self, per_page=3):
        url = f"{self.base_url}/wp-json/wc/v3/products"
        params = {
            "per_page": per_page,
            "orderby": "date",
            "order": "desc"
        }
        
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"WC API Error {response.status}: {text}")
                
                return await response.json()

    # --- این بخش جدید است که اضافه شد ---
    async def create_simple_product(self, data: dict):
        url = f"{self.base_url}/wp-json/wc/v3/products"
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.post(url, json=data) as response:
                # کدهای 200 و 201 برای موفقیت‌آمیز بودن ثبت هستند
                if response.status not in [200, 201]:
                    text = await response.text()
                    raise Exception(f"WC API Error {response.status}: {text}")
                
                return await response.json()
