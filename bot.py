import asyncio
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
)

from config import Config
from utils import (
    logger,
    desktop_notify,
    play_alert_sound,
    stop_alert,
    save_cookies,
    load_cookies,
    countdown,
)

HK_TICKETING_BASE = "https://www.hkticketing.com"
LIVE_NATION_DOMAINS = ["livenation.hk", "livenation.com"]
ARTIST_TOUR_DOMAINS = ["theweeknd.com"]
QUEUE_IT_DOMAINS = ["queue-it.com", "queue-it.net", "queue-it.cloud"]


class HKTicketingBot:

    HK_LOGIN_INDICATOR = "div.title___UIF7d"

    def __init__(self, config: Config, browser_name: str = "chromium"):
        self.config = config
        self.browser_name = browser_name
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.sound_proc = None
        self.cookie_name = f"hkticketing_{browser_name}"

    async def setup(self):
        logger.info(f"🚀 启动浏览器 [{self.browser_name}]...")
        self.playwright = await async_playwright().start()

        browser_type_map = {
            "chromium": self.playwright.chromium,
            "firefox": self.playwright.firefox,
            "webkit": self.playwright.webkit,
        }
        browser_launcher = browser_type_map.get(self.browser_name, self.playwright.chromium)

        user_data_dir = Path(f"./browser_data/{self.browser_name}")
        user_data_dir.mkdir(parents=True, exist_ok=True)

        if self.browser_name == "chromium":
            self.context = await browser_launcher.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=self.config.bot.headless,
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="zh-HK",
                timezone_id="Asia/Hong_Kong",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
        else:
            self.browser = await browser_launcher.launch(
                headless=self.config.bot.headless,
            )
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="zh-HK",
                timezone_id="Asia/Hong_Kong",
            )

        await self._inject_stealth()
        self.page = await self.context.new_page()
        logger.info(f"✅ 浏览器 [{self.browser_name}] 就绪")

    async def _inject_stealth(self):
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({state: Notification.permissionState}) :
                    originalQuery(parameters)
            );
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-HK', 'zh-TW', 'zh', 'en-US', 'en'],
            });
        """)

    async def login(self):
        await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if await load_cookies(self.context, self.cookie_name, self.config.bot.cookie_dir):
            await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            if await self._check_logged_in():
                logger.info("✅ Cookie 有效, 已登录")
                return True
            logger.info("⚠️ Cookie 已过期")

        await self._manual_login()
        return True

    async def _check_logged_in(self, navigate: bool = True):
        try:
            if navigate:
                await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(1)

            elem = await self.page.query_selector(self.HK_LOGIN_INDICATOR)
            if elem:
                text = (await elem.inner_text()).strip()
                if not text:
                    return False
                if text == "登录" or text.lower() == "login":
                    return False
                logger.info("已登录")
                return True
            return False
        except Exception:
            return False

    async def _manual_login(self):
        logger.info("🔑 请在弹出的浏览器窗口中登录快达票...")
        desktop_notify("抢票助手", "请手动登录快达票账户")

        try:
            await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        logger.info("⏳ 等待登录 (最长5分钟, 每15秒检查一次)...")

        for minute in range(5):
            for _ in range(5):
                await asyncio.sleep(3)
                if await self._check_logged_in(navigate=False):
                    logger.info("✅ 登录成功, Cookie 已保存")
                    await save_cookies(self.context, self.cookie_name, self.config.bot.cookie_dir)
                    return

            logger.info(f"⏰ 第{minute+1}分钟, 检查登录状态...")
            if await self._check_logged_in(navigate=True):
                logger.info("✅ 登录成功, Cookie 已保存")
                await save_cookies(self.context, self.cookie_name, self.config.bot.cookie_dir)
                return

            left = 4 - minute
            if left > 0:
                logger.info(f"   未检测到登录, 剩余约 {left} 分钟...")

        logger.error("❌ 登录超时 (5分钟)")

    async def monitor_event_page(self, event_url: str, sale_time: datetime):
        logger.info(f"👀 监控页面: {event_url}")

        while True:
            try:
                await self.page.goto(event_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1)
            except PlaywrightTimeout:
                logger.warning("⚠️ 页面加载超时, 重试...")
                continue

            # Live Nation 页面 → 点击跳转到快达票
            if self._is_livenation(self.page.url):
                if await self._click_livenation_link():
                    logger.info("🎫 已从 Live Nation 跳转到快达票")
                    event_url = self.page.url
                continue

            # 艺人官网 tour 页面 → 找香港站链接并点击
            if self._is_artist_tour(self.page.url):
                if await self._click_artist_tour_link():
                    logger.info("🎫 已从艺人官网跳转到快达票")
                    event_url = self.page.url
                continue

            if self._is_queue_it(self.page.url):
                logger.info("🔄 进入 Queue-it 排队...")
                await self._handle_queue()
                continue

            if await self._detect_captcha():
                await self._notify_captcha()
                await self._wait_for_captcha_solve()

            if await self._find_buy_button():
                logger.info("🎫 发现购票入口")
                return True

            now = datetime.now()
            if now < sale_time:
                time_left = (sale_time - now).total_seconds()
                if time_left > 60:
                    logger.info(f"⏳ 距开售 {int(time_left)} 秒")
                    await asyncio.sleep(min(self.config.bot.poll_interval, time_left - 55))
                else:
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(self.config.bot.poll_interval)

    def _is_queue_it(self, url: str):
        return any(domain in url.lower() for domain in QUEUE_IT_DOMAINS)

    def _is_livenation(self, url: str):
        return any(domain in url.lower() for domain in LIVE_NATION_DOMAINS)

    def _is_artist_tour(self, url: str):
        return any(domain in url.lower() for domain in ARTIST_TOUR_DOMAINS)

    async def _click_artist_tour_link(self):
        """在艺人官网 tour 页面上找香港站链接并点击"""
        link_selectors = [
            'a:has-text("Hong Kong")',
            'a:has-text("Kai Tak")',
            'a:has-text("Tickets")',
            '.tour-dates a',
            '[data-city*="hong"]',
        ]
        for sel in link_selectors:
            try:
                elem = await self.page.wait_for_selector(sel, timeout=3000)
                if elem:
                    href = await elem.get_attribute("href")
                    logger.info(f"👉 点击艺人官网链接: {href}")
                    await elem.click()
                    await asyncio.sleep(3)
                    return True
            except PlaywrightTimeout:
                continue
        return False

    async def _click_livenation_link(self):
        """在 Live Nation 页面上找到跳转快达票的按钮并点击"""
        link_selectors = [
            'a:has-text("Get Tickets")',
            'a:has-text("Buy Tickets")',
            'a:has-text("購票")',
            'a:has-text("Book Now")',
            '[data-track="tickets"]',
            '.ticket-link a',
            '.buy-tickets a',
        ]
        for sel in link_selectors:
            try:
                elem = await self.page.wait_for_selector(sel, timeout=3000)
                if elem:
                    href = await elem.get_attribute("href")
                    logger.info(f"👉 点击 Live Nation 购票链接: {href}")
                    await elem.click()
                    await asyncio.sleep(3)
                    return True
            except PlaywrightTimeout:
                continue
        return False

    async def _handle_queue(self):
        logger.info("📋 进入虚拟等候室, 等待放行...")
        start = time.time()
        last_queue_id = None

        while True:
            await asyncio.sleep(2)
            if not self._is_queue_it(self.page.url):
                logger.info("✅ 排队结束, 已放行")
                return

            try:
                content = await self.page.content()
                queue_match = re.search(r'queue[_\s-]?id["\':\s]+(\w+)', content, re.I)
                if queue_match and queue_match.group(1) != last_queue_id:
                    last_queue_id = queue_match.group(1)
                    logger.info(f"📍 排队ID: {last_queue_id}")
            except Exception:
                pass

            if time.time() - start > 1800 and (time.time() - start) % 300 < 3:
                desktop_notify("抢票助手", "仍在排队中, 请保持浏览器开启")

    async def _detect_captcha(self):
        selectors = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="google.com/recaptcha"]',
            'div.g-recaptcha',
            'div[data-sitekey]',
        ]
        for sel in selectors:
            if await self.page.query_selector(sel):
                return True

        content = await self.page.content()
        keywords = ["我不是机器人", "I'm not a robot", "recaptcha"]
        return any(kw.lower() in content.lower() for kw in keywords)

    async def _notify_captcha(self):
        logger.warning("🤖 请手动完成 reCAPTCHA 验证!")
        if self.config.bot.desktop_notification:
            desktop_notify("抢票助手 - 需要验证", "请完成 reCAPTCHA 人机验证!")
        if self.config.bot.sound_alert:
            self.sound_proc = play_alert_sound(repeat=True, interval=self.config.bot.sound_repeat)

    async def _wait_for_captcha_solve(self, timeout: int = 120):
        logger.info("⏳ 等待完成验证 (最长 120 秒)...")
        start = time.time()

        while time.time() - start < timeout:
            await asyncio.sleep(1)
            if not await self._detect_captcha():
                logger.info("✅ 验证通过")
                stop_alert(self.sound_proc)
                self.sound_proc = None
                return

            elapsed = int(time.time() - start)
            if elapsed % 10 == 0 and elapsed > 0:
                logger.warning(f"⏰ 已等待 {elapsed} 秒...")

        logger.error("❌ 验证超时")
        stop_alert(self.sound_proc)
        self.sound_proc = None

    async def _find_buy_button(self):
        keywords = [
            "立即購買", "立即购买", "Buy Tickets", "購票",
            "立即訂票", "立即订票", "優先訂票", "优先订票",
            "Book Now", "Get Tickets", "Purchase",
        ]
        try:
            content = await self.page.content()
            return any(kw.lower() in content.lower() for kw in keywords)
        except Exception:
            return False

    async def checkout(self):
        logger.info("🛒 开始快速选票结账...")
        tkt = self.config.ticket

        try:
            # 艺人优先购需要输入 code
            if tkt.presale_code and await self._detect_presale_code_field():
                await self._enter_presale_code(tkt.presale_code)

            if tkt.preferred_date:
                await self._select_date(tkt.preferred_date)

            selected = False
            for tier in tkt.price_tiers:
                if await self._select_price_tier(tier):
                    selected = True
                    logger.info(f"✅ 已选择: {tier}")
                    break

            if not selected:
                logger.error("❌ 目标票价均不可用")
                return False

            await self._select_quantity(tkt.quantity)
            await self._click_next()

            await asyncio.sleep(1)
            if await self._detect_captcha():
                await self._notify_captcha()
                await self._wait_for_captcha_solve()

            if self.config.account.card_number:
                await self._fill_payment()

            await self._notify_final_confirm()
            logger.info("🎉 选票完成, 请在浏览器中确认支付")
            return True

        except Exception as e:
            logger.error(f"结账出错: {e}")
            return False

    async def _detect_presale_code_field(self):
        """检测页面上是否有优先购验证码输入框"""
        selectors = [
            'input[name*="code"]',
            'input[name*="promo"]',
            'input[name*="presale"]',
            'input[placeholder*="code"i]',
            'input[placeholder*="代碼"i]',
            'input[placeholder*="代碼"i]',
        ]
        for sel in selectors:
            if await self.page.query_selector(sel):
                return True
        return False

    async def _enter_presale_code(self, code: str):
        """输入优先购验证码"""
        logger.info(f"🔑 输入优先购验证码...")
        selectors = [
            'input[name*="code"]',
            'input[name*="promo"]',
            'input[name*="presale"]',
            'input[placeholder*="code"i]',
            'input[placeholder*="代碼"i]',
        ]
        for sel in selectors:
            elem = await self.page.query_selector(sel)
            if elem:
                await elem.fill(code)
                logger.info(f"✅ 已输入验证码")
                # 提交按钮
                for btn_text in ["提交", "確認", "Submit", "Verify"]:
                    btn = await self.page.query_selector(
                        f'button:has-text("{btn_text}"), input[type="submit"][value*="{btn_text}"i]'
                    )
                    if btn:
                        await btn.click()
                        await asyncio.sleep(2)
                        return
                return

    async def _select_date(self, date: str):
        selectors = [
            f'button:has-text("{date}")',
            f'a:has-text("{date}")',
            f'[value*="{date}"]',
            f'option:has-text("{date}")',
        ]
        for sel in selectors:
            try:
                elem = await self.page.wait_for_selector(sel, timeout=3000)
                if elem:
                    await elem.click()
                    await asyncio.sleep(1)
                    return
            except PlaywrightTimeout:
                continue

    async def _select_price_tier(self, tier: str):
        price = tier.replace("HKD", "").strip()
        selectors = [
            f'text="{tier}"',
            f'text="{price}"',
            f'[value*="{price}"]',
            f'option:has-text("{price}")',
            f'label:has-text("{price}")',
        ]
        for sel in selectors:
            try:
                elem = await self.page.wait_for_selector(sel, timeout=2000)
                if elem:
                    await elem.click()
                    await asyncio.sleep(0.5)
                    return True
            except PlaywrightTimeout:
                continue
        return False

    async def _select_quantity(self, quantity: int):
        qty_str = str(quantity)
        selectors = [
            f'select:has(option[value="{qty_str}"])',
            f'input[type="number"]',
            f'[name*="qty"]',
            f'[name*="quantity"]',
        ]
        for sel in selectors:
            try:
                elem = await self.page.wait_for_selector(sel, timeout=2000)
                if elem:
                    tag = await elem.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        await elem.select_option(qty_str)
                    elif tag == "input":
                        await elem.fill(qty_str)
                    await asyncio.sleep(0.3)
                    return
            except PlaywrightTimeout:
                continue

        qty_btn = await self.page.query_selector(f'button:has-text("{qty_str}")')
        if qty_btn:
            await qty_btn.click()

    async def _click_next(self):
        keywords = [
            "下一步", "繼續", "继续", "Next", "Continue",
            "結賬", "结账", "Checkout", "Proceed",
            "加入購物車", "加入购物车", "Add to Cart",
        ]
        for kw in keywords:
            try:
                btn = await self.page.wait_for_selector(
                    f'button:has-text("{kw}"), a:has-text("{kw}"), input[value*="{kw}"]',
                    timeout=2000,
                )
                if btn:
                    await btn.click()
                    await asyncio.sleep(2)
                    return
            except PlaywrightTimeout:
                continue

    async def _fill_payment(self):
        acc = self.config.account
        fill_map = {
            '[name*="cardnumber"]': acc.card_number,
            '[name*="cc"]': acc.card_number,
            '[name*="expiry"]': f"{acc.card_expiry_month}/{acc.card_expiry_year}",
            '[name*="exp"]': f"{acc.card_expiry_month}/{acc.card_expiry_year}",
            '[name*="cvv"]': acc.card_cvv,
            '[name*="cvc"]': acc.card_cvv,
            '[name*="holdername"]': acc.card_holder_name,
            '[name*="name"]': acc.card_holder_name,
        }
        for selector, value in fill_map.items():
            if not value:
                continue
            try:
                elem = await self.page.query_selector(selector)
                if elem:
                    await elem.fill(value)
            except Exception:
                pass

    async def _notify_final_confirm(self):
        logger.warning("🛎️  请在浏览器中确认订单并完成支付!")
        desktop_notify("抢票助手 - 请确认", "订单已准备好，请尽快确认支付!")
        if self.config.bot.sound_alert:
            self.sound_proc = play_alert_sound(repeat=True, interval=3)
            await asyncio.sleep(60)
            stop_alert(self.sound_proc)

    async def run(self, event_url: str, sale_time: datetime):
        try:
            await self.setup()
            await self.login()

            now = datetime.now()
            wait_seconds = (sale_time - now).total_seconds()
            if wait_seconds > 0:
                logger.info(f"⏳ 距开售 {int(wait_seconds)} 秒")
                if wait_seconds > 60:
                    countdown(int(wait_seconds - 50), "距开售")

            if not await self.monitor_event_page(event_url, sale_time):
                logger.error("未能进入购票页面")
                return False

            return await self.checkout()

        except Exception as e:
            logger.error(f"运行出错: {e}")
            return False
        finally:
            stop_alert(self.sound_proc)
            logger.info("主流程结束, 浏览器保持开启...")
