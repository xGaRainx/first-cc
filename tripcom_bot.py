"""Trip.com 移动端抢票助手 (iPhone 模拟)"""
import asyncio
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from utils import logger, desktop_notify, play_alert_sound, stop_alert, save_cookies, load_cookies

TRIP_COM_BASE = "https://hk.trip.com"


class TripComBot:

    def __init__(self, event_url: str, sale_time: datetime, ticket_tier: str = "",
                 quantity: int = 2, headless: bool = False, sound_alert: bool = True):
        self.event_url = event_url
        self.sale_time = sale_time
        self.ticket_tier = ticket_tier
        self.quantity = quantity
        self.headless = headless
        self.sound_alert = sound_alert
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.sound_proc = None

    async def setup(self):
        logger.info("📱 启动 Trip.com 移动端浏览器...")
        self.playwright = await async_playwright().start()

        iphone = self.playwright.devices["iPhone 14 Pro"]
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir="./browser_data/trip_com",
            headless=self.headless,
            **iphone,
            locale="zh-HK",
            timezone_id="Asia/Hong_Kong",
            args=["--disable-blink-features=AutomationControlled"],
        )

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
        """)
        self.page = await self.context.new_page()
        logger.info("✅ Trip.com 浏览器就绪")

    async def login(self):
        await self.page.goto(TRIP_COM_BASE, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if await load_cookies(self.context, "trip_com"):
            await self.page.goto(TRIP_COM_BASE, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            if await self._check_logged_in():
                logger.info("✅ Trip.com Cookie 有效")
                return True

        logger.info("🔑 请手动登录 Trip.com...")
        desktop_notify("Trip.com 抢票", "请手动登录")
        for _ in range(300):
            await asyncio.sleep(1)
            if await self._check_logged_in():
                logger.info("✅ Trip.com 登录成功")
                await save_cookies(self.context, "trip_com")
                return True

        logger.error("❌ Trip.com 登录超时")
        return False

    async def _check_logged_in(self):
        try:
            content = await self.page.content()
            for kw in ["我的订单", "My Orders", "会员中心"]:
                if kw.lower() in content.lower():
                    return True
            for kw in ["登入", "Sign in", "登录"]:
                if kw.lower() in content.lower():
                    if await self.page.query_selector(f'text="{kw}"'):
                        return False
            return True
        except Exception:
            return False

    async def monitor(self):
        logger.info(f"👀 Trip.com 监控: {self.event_url}")
        while True:
            try:
                await self.page.goto(self.event_url, wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(1.5)
            except PlaywrightTimeout:
                logger.warning("⚠️ Trip.com 页面超时")
                continue

            if "app-download" in self.page.url.lower():
                logger.error("❌ Trip.com 强制 App 访问, 网页端不可用")
                return False

            if await self._find_buy_button():
                logger.info("🎫 Trip.com 发现购票入口")
                return True

            if await self._detect_captcha():
                await self._notify_captcha()
                await self._wait_for_captcha()

            now = datetime.now()
            if now < self.sale_time:
                wait = (self.sale_time - now).total_seconds()
                await asyncio.sleep(min(2, wait))
            await asyncio.sleep(1)

    async def _find_buy_button(self):
        try:
            content = await self.page.content()
            return any(kw.lower() in content.lower()
                       for kw in ["立即購買", "Book Now", "Buy", "搶票"])
        except Exception:
            return False

    async def _detect_captcha(self):
        try:
            return await self.page.query_selector(
                'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey]') is not None
        except Exception:
            return False

    async def _notify_captcha(self):
        logger.warning("🤖 Trip.com 需要验证")
        desktop_notify("Trip.com 抢票", "请完成验证")
        if self.sound_alert:
            self.sound_proc = play_alert_sound(repeat=True)

    async def _wait_for_captcha(self, timeout: int = 120):
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            await asyncio.sleep(1)
            if not await self._detect_captcha():
                logger.info("✅ Trip.com 验证通过")
                stop_alert(self.sound_proc)
                return

    async def checkout(self):
        logger.info("🛒 Trip.com 快速选票...")
        if self.ticket_tier:
            try:
                btn = await self.page.wait_for_selector(f'text="{self.ticket_tier}"', timeout=5000)
                if btn:
                    await btn.click()
            except PlaywrightTimeout:
                pass

        qty_str = str(self.quantity)
        try:
            btn = await self.page.wait_for_selector(f'text="{qty_str}"', timeout=3000)
            if btn:
                await btn.click()
        except PlaywrightTimeout:
            pass

        for kw in ["下一步", "Next", "確認", "Book Now"]:
            try:
                btn = await self.page.wait_for_selector(
                    f'button:has-text("{kw}"), a:has-text("{kw}")', timeout=2000)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
            except PlaywrightTimeout:
                continue

        desktop_notify("Trip.com 抢票", "请确认订单并完成支付")

    async def run(self):
        try:
            await self.setup()
            await self.login()
            if await self.monitor():
                await self.checkout()
        except Exception as e:
            logger.error(f"Trip.com 出错: {e}")
        finally:
            stop_alert(self.sound_proc)
            logger.info("Trip.com 浏览器保持开启...")


async def run_trip_com(event_url: str, sale_time_str: str, tier: str = "",
                       qty: int = 2, headless: bool = False):
    from config import setup_logging
    setup_logging("INFO")
    sale_time = datetime.strptime(sale_time_str, "%Y-%m-%d %H:%M:%S")
    bot = TripComBot(event_url=event_url, sale_time=sale_time, ticket_tier=tier,
                     quantity=qty, headless=headless)
    await bot.run()
