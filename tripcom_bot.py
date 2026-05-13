"""
Trip.com 优先购抢票助手 (移动端模拟)

Trip.com 优先购仅限 App, 本脚本使用 Playwright 移动端模拟
尝试通过移动网页版访问。如遇强制跳转 App, 则只能手动操作。
"""
import asyncio
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from utils import (
    logger, desktop_notify, play_alert_sound, stop_alert,
    save_cookies, load_cookies,
)


TRIP_COM_BASE = "https://hk.trip.com"


class TripComBot:
    """Trip.com 移动端抢票助手"""

    def __init__(
        self,
        event_url: str,
        sale_time: datetime,
        ticket_tier: str = "",
        quantity: int = 2,
        headless: bool = False,
        sound_alert: bool = True,
    ):
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

    async def setup(self) -> None:
        """初始化移动端浏览器"""
        logger.info("📱 启动 Trip.com 移动端浏览器...")

        self.playwright = await async_playwright().start()

        # 模拟 iPhone 14 Pro
        iphone = self.playwright.devices["iPhone 14 Pro"]
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir="./browser_data/trip_com",
            headless=self.headless,
            **iphone,
            locale="zh-HK",
            timezone_id="Asia/Hong_Kong",
            args=["--disable-blink-features=AutomationControlled"],
        )

        # 反检测
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
        """)

        self.page = await self.context.new_page()
        logger.info("✅ Trip.com 浏览器就绪")

    async def login(self) -> bool:
        """登录 Trip.com"""
        await self.page.goto(TRIP_COM_BASE, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if await load_cookies(self.context, "trip_com"):
            await self.page.goto(TRIP_COM_BASE, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            if await self._check_logged_in():
                logger.info("✅ Trip.com Cookie 有效, 已登录")
                return True

        logger.info("🔑 请在手机模拟窗口中手动登录 Trip.com...")
        desktop_notify("Trip.com 抢票", "请手动登录 Trip.com 账户")

        for _ in range(300):
            await asyncio.sleep(1)
            if await self._check_logged_in():
                logger.info("✅ Trip.com 登录成功!")
                await save_cookies(self.context, "trip_com")
                return True

        logger.error("❌ Trip.com 登录超时")
        return False

    async def _check_logged_in(self) -> bool:
        """检查 Trip.com 登录状态"""
        try:
            content = await self.page.content()
            logged_out_indicators = ["登入", "Sign in", "登录"]
            logged_in_indicators = ["我的订单", "My Orders", "会员中心"]
            for kw in logged_in_indicators:
                if kw.lower() in content.lower():
                    return True
            # 如果有明显的登录入口, 说明未登录
            for kw in logged_out_indicators:
                if kw.lower() in content.lower():
                    btn = await self.page.query_selector(f'text="{kw}"')
                    if btn:
                        return False
            return True
        except Exception:
            return False

    async def monitor(self) -> bool:
        """监控活动页面直到可购票"""
        logger.info(f"👀 Trip.com 监控: {self.event_url}")

        while True:
            try:
                await self.page.goto(self.event_url, wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(1.5)
            except PlaywrightTimeout:
                logger.warning("⚠️ Trip.com 页面超时")
                continue

            current_url = self.page.url

            # 检查是否被强制跳转 App 下载页
            if "app-download" in current_url.lower() or "download" in current_url.lower():
                logger.error("❌ Trip.com 强制 App 访问, 网页端无法购票!")
                return False

            # 检查是否有购票按钮
            if await self._find_buy_button():
                logger.info("🎫 Trip.com 发现购票入口!")
                return True

            # 检查 reCAPTCHA
            if await self._detect_captcha():
                await self._notify_captcha()
                await self._wait_for_captcha()

            now = datetime.now()
            if now < self.sale_time:
                wait = (self.sale_time - now).total_seconds()
                logger.info(f"⏳ Trip.com 距开售 {int(wait)} 秒")
                await asyncio.sleep(min(2, wait))

            await asyncio.sleep(1)

    async def _find_buy_button(self) -> bool:
        buy_kw = ["立即購買", "立即购买", "Book Now", "Buy", "搶票", "购票"]
        try:
            content = await self.page.content()
            return any(kw.lower() in content.lower() for kw in buy_kw)
        except Exception:
            return False

    async def _detect_captcha(self) -> bool:
        try:
            return await self.page.query_selector(
                'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey]'
            ) is not None
        except Exception:
            return False

    async def _notify_captcha(self) -> None:
        logger.warning("🤖 Trip.com 需要验证, 请手动完成!")
        desktop_notify("Trip.com 抢票", "请完成人机验证!")
        if self.sound_alert:
            self.sound_proc = play_alert_sound(repeat=True)

    async def _wait_for_captcha(self, timeout: int = 120) -> None:
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            await asyncio.sleep(1)
            if not await self._detect_captcha():
                logger.info("✅ Trip.com 验证通过!")
                stop_alert(self.sound_proc)
                return

    async def checkout(self) -> None:
        """快速选票 (移动端页面结构与 PC 端有差异)"""
        logger.info("🛒 Trip.com 快速选票...")

        # 选择票价档位
        if self.ticket_tier:
            try:
                tier_btn = await self.page.wait_for_selector(
                    f'text="{self.ticket_tier}"', timeout=5000
                )
                if tier_btn:
                    await tier_btn.click()
                    logger.info(f"✅ 选择: {self.ticket_tier}")
            except PlaywrightTimeout:
                pass

        # 选择数量
        qty_str = str(self.quantity)
        try:
            qty_btn = await self.page.wait_for_selector(f'text="{qty_str}"', timeout=3000)
            if qty_btn:
                await qty_btn.click()
        except PlaywrightTimeout:
            pass

        # 下一步
        next_btns = ["下一步", "Next", "確認", "确认", "Book Now"]
        for kw in next_btns:
            try:
                btn = await self.page.wait_for_selector(
                    f'button:has-text("{kw}"), a:has-text("{kw}")', timeout=2000
                )
                if btn:
                    await btn.click()
                    logger.info(f"👉 Trip.com: {kw}")
                    await asyncio.sleep(1)
            except PlaywrightTimeout:
                continue

        desktop_notify("Trip.com 抢票", "请确认订单并完成支付!")

    async def run(self) -> bool:
        try:
            await self.setup()
            await self.login()
            success = await self.monitor()
            if success:
                await self.checkout()
            return success
        except Exception as e:
            logger.error(f"Trip.com 出错: {e}")
            return False
        finally:
            stop_alert(self.sound_proc)
            logger.info("Trip.com 浏览器保持开启...")


async def run_trip_com(
    event_url: str,
    sale_time_str: str,
    tier: str = "",
    qty: int = 2,
    headless: bool = False,
):
    """启动 Trip.com 抢票"""
    from config import setup_logging
    setup_logging("INFO")

    sale_time = datetime.strptime(sale_time_str, "%Y-%m-%d %H:%M:%S")
    bot = TripComBot(
        event_url=event_url,
        sale_time=sale_time,
        ticket_tier=tier,
        quantity=qty,
        headless=headless,
    )
    await bot.run()
