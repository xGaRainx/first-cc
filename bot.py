"""
快达票 HK Ticketing 半自动抢票机器人

流程:
  1. 启动浏览器 → 加载已保存的登录 Cookie
  2. 在开售时间前进入监控页面
  3. 如遇 Queue-it 排队 → 自动等待
  4. 检测到 reCAPTCHA → 声音+通知提醒用户手动完成
  5. 用户完成验证后 → 自动快速选票结账
"""
import asyncio
import time
import re
import subprocess
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

from config import Config, SalePhase
from utils import (
    logger,
    desktop_notify,
    play_alert_sound,
    stop_alert,
    save_cookies,
    load_cookies,
    countdown,
)

# 快达票关键 URL
HK_TICKETING_BASE = "https://www.hkticketing.com"
HK_TICKETING_LOGIN = f"{HK_TICKETING_BASE}/login"  # 可能变化
QUEUE_IT_DOMAINS = ["queue-it.com", "queue-it.net", "queue-it.cloud"]


class HKTicketingBot:
    """快达票抢票机器人"""

    def __init__(self, config: Config, browser_name: str = "chromium"):
        self.config = config
        self.browser_name = browser_name
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.sound_proc = None
        self.captcha_solved = False

        # 每个浏览器实例的 Cookie 文件名
        self.cookie_name = f"hkticketing_{browser_name}"

    async def setup(self) -> None:
        """初始化 Playwright 和浏览器"""
        logger.info(f"🚀 启动浏览器 [{self.browser_name}]...")

        self.playwright = await async_playwright().start()

        # 选择浏览器类型
        browser_type_map = {
            "chromium": self.playwright.chromium,
            "firefox": self.playwright.firefox,
            "webkit": self.playwright.webkit,
        }
        browser_launcher = browser_type_map.get(
            self.browser_name, self.playwright.chromium
        )

        # 使用持久化上下文 (保存登录状态)
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
                # 禁用自动化特征
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
        else:
            # Firefox/WebKit 用 launch + new_context
            self.browser = await browser_launcher.launch(
                headless=self.config.bot.headless,
                args=["--disable-blink-features=AutomationControlled"]
                if self.browser_name != "firefox"
                else None,
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

        # 注入反检测脚本
        await self._inject_stealth()

        self.page = await self.context.new_page()
        logger.info(f"✅ 浏览器 [{self.browser_name}] 就绪")

    async def _inject_stealth(self) -> None:
        """注入反检测脚本, 隐藏自动化特征"""
        stealth_js = """
        // 覆盖 navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => false });

        // 伪造 chrome 对象
        window.chrome = { runtime: {} };

        // 伪造权限查询
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({state: Notification.permissionState}) :
                originalQuery(parameters)
        );

        // 伪造插件
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // 伪造语言
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-HK', 'zh-TW', 'zh', 'en-US', 'en'],
        });
        """
        await self.context.add_init_script(stealth_js)

    async def login(self) -> bool:
        """登录快达票 (如果 Cookie 无效则手动登录)"""
        await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 尝试加载 Cookie
        if await load_cookies(self.context, self.cookie_name, self.config.bot.cookie_dir):
            await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # 检查是否已登录 (查找登录按钮或用户头像)
            logged_in = await self._check_logged_in()
            if logged_in:
                logger.info("✅ Cookie 有效, 已登录")
                return True
            else:
                logger.info("⚠️ Cookie 已过期, 需要重新登录")

        # Cookie 无效或无 Cookie — 需要用户手动登录
        await self._manual_login()
        return True

    # 快达票登录状态元素: 未登录显示"登录", 已登录显示用户名
    HK_LOGIN_INDICATOR = "div.title___UIF7d"

    async def _check_logged_in(self, navigate: bool = True) -> bool:
        """检查是否已登录快达票"""
        try:
            if navigate:
                await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(1)

            elem = await self.page.query_selector(self.HK_LOGIN_INDICATOR)
            if elem:
                text = await elem.inner_text()
                text = text.strip()
                if not text:
                    return False
                # 未登录时显示"登录"
                if text == "登录" or text.lower() == "login":
                    return False
                # 已登录时显示用户名
                logger.info(f"检测到已登录, 用户名: {text}")
                return True

            return False
        except Exception:
            return False

    async def _manual_login(self) -> None:
        """引导用户手动登录 (每15秒回首页检查一次登录状态)"""
        logger.info("🔑 请在弹出的浏览器窗口中手动登录快达票...")
        desktop_notify("抢票助手", "请手动登录快达票账户")

        try:
            await self.page.goto(HK_TICKETING_BASE, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        logger.info("⏳ 等待你完成登录 (每15秒检查一次, 有5分钟时间)...")
        logger.info("   💡 在浏览器里点「登入」→ 输入账号密码 → 登录即可")

        for minute in range(5):
            # 等待期间每3秒静默检查一次当前页面
            for _ in range(5):  # 5 * 3 = 15秒一个周期
                await asyncio.sleep(3)
                if await self._check_logged_in(navigate=False):
                    logger.info("✅ 登录成功!")
                    await save_cookies(
                        self.context, self.cookie_name, self.config.bot.cookie_dir
                    )
                    return

            # 15秒后回到首页检查 (此时如果用户已登录, 首页会显示账户信息)
            logger.info(f"⏰ 第{minute+1}分钟, 回到首页检查登录状态...")
            if await self._check_logged_in(navigate=True):
                logger.info("✅ 登录成功!")
                await save_cookies(
                    self.context, self.cookie_name, self.config.bot.cookie_dir
                )
                return

            left = 4 - minute
            if left > 0:
                logger.info(f"   未检测到登录, 剩余约 {left} 分钟...")

        logger.error("❌ 登录超时 (5分钟)")

    async def monitor_event_page(self, event_url: str, sale_time: datetime) -> bool:
        """
        监控活动页面, 处理排队和验证

        返回 True 表示成功进入购票页面
        """
        logger.info(f"👀 开始监控: {event_url}")

        # 在开售前持续刷新, 直到购票按钮出现
        while True:
            try:
                await self.page.goto(event_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1)
            except PlaywrightTimeout:
                logger.warning("⚠️ 页面加载超时, 重试...")
                continue

            # 1. 检查是否被重定向到 Queue-it
            current_url = self.page.url
            if self._is_queue_it(current_url):
                logger.info("🔄 进入 Queue-it 排队系统...")
                await self._handle_queue()
                continue  # 排队结束重新检查

            # 2. 检查是否有 reCAPTCHA
            if await self._detect_captcha():
                logger.warning("🤖 检测到 reCAPTCHA, 等待用户完成验证...")
                await self._notify_captcha()
                await self._wait_for_captcha_solve()

            # 3. 检查是否有购票按钮
            if await self._find_buy_button():
                logger.info("🎫 发现购票入口!")
                return True

            # 4. 还没开放 — 等待后重试
            now = datetime.now()
            if now < sale_time:
                time_left = (sale_time - now).total_seconds()
                if time_left > 60:
                    logger.info(f"⏳ 距开售还有 {int(time_left)} 秒, 等待中...")
                    await asyncio.sleep(min(self.config.bot.poll_interval, time_left - 55))
                else:
                    # 最后一分钟, 加快轮询
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(self.config.bot.poll_interval)

    def _is_queue_it(self, url: str) -> bool:
        """判断是否在 Queue-it 排队页面"""
        return any(domain in url.lower() for domain in QUEUE_IT_DOMAINS)

    async def _handle_queue(self) -> None:
        """处理 Queue-it 排队等待"""
        logger.info("📋 进入虚拟等候室, 等待系统放行...")

        # 读取排队进度 (如果有)
        last_queue_id = None
        start = time.time()

        while True:
            await asyncio.sleep(2)
            current_url = self.page.url

            # 检查是否被放行回主站
            if not self._is_queue_it(current_url):
                logger.info("✅ 排队结束, 已放行!")
                return

            # 尝试获取排队状态
            try:
                content = await self.page.content()
                # Queue-it 可能显示排队ID和预计等待时间
                queue_match = re.search(r'queue[_\s-]?id["\':\s]+(\w+)', content, re.I)
                wait_match = re.search(r'(?:wait|等待|预计)[^\d]*(\d+)[^\d]*(\w+)', content)
                if queue_match and queue_match.group(1) != last_queue_id:
                    last_queue_id = queue_match.group(1)
                    logger.info(f"📍 排队ID: {last_queue_id}")
                if wait_match:
                    logger.info(f"⏱️ 预计等待: {wait_match.group(0)}")
            except Exception:
                pass

            # 排队超过30分钟 → 通知用户
            if time.time() - start > 1800 and (time.time() - start) % 300 < 3:
                desktop_notify("抢票助手", "仍在排队中, 请保持浏览器开启")

    async def _detect_captcha(self) -> bool:
        """检测页面是否有 reCAPTCHA"""
        try:
            # 检查常见的 reCAPTCHA 元素
            captcha_selectors = [
                'iframe[src*="recaptcha"]',
                'iframe[src*="google.com/recaptcha"]',
                'div.g-recaptcha',
                'div[data-sitekey]',
                '#recaptcha',
                '.g-recaptcha',
            ]
            for selector in captcha_selectors:
                element = await self.page.query_selector(selector)
                if element:
                    return True
            # 检查页面文字
            content = await self.page.content()
            captcha_keywords = ["我不是机器人", "我不是機械人", "I'm not a robot", "recaptcha"]
            for kw in captcha_keywords:
                if kw.lower() in content.lower():
                    return True
        except Exception:
            pass
        return False

    async def _notify_captcha(self) -> None:
        """发出 reCAPTCHA 提醒 (通知 + 声音)"""
        logger.warning("=" * 50)
        logger.warning("🤖 请手动完成 reCAPTCHA 验证!")
        logger.warning("=" * 50)

        if self.config.bot.desktop_notification:
            desktop_notify("🤖 抢票助手 - 需要验证", "请完成 reCAPTCHA 人机验证!")

        if self.config.bot.sound_alert:
            self.sound_proc = play_alert_sound(
                repeat=True, interval=self.config.bot.sound_repeat
            )

    async def _wait_for_captcha_solve(self, timeout: int = 120) -> None:
        """等待用户手动完成 reCAPTCHA"""
        logger.info("⏳ 等待用户完成验证 (最长 120 秒)...")
        start = time.time()

        while time.time() - start < timeout:
            await asyncio.sleep(1)

            # 检查 reCAPTCHA 是否消失
            if not await self._detect_captcha():
                logger.info("✅ reCAPTCHA 验证通过!")
                stop_alert(self.sound_proc)
                self.sound_proc = None
                return

            # 每10秒提醒一次
            elapsed = int(time.time() - start)
            if elapsed % 10 == 0 and elapsed > 0:
                logger.warning(f"⏰ 已等待 {elapsed} 秒, 请尽快完成验证...")

        logger.error("❌ reCAPTCHA 验证超时!")
        stop_alert(self.sound_proc)
        self.sound_proc = None

    async def _find_buy_button(self) -> bool:
        """查找购票/立即购买按钮"""
        buy_keywords = [
            "立即購買", "立即购买", "Buy Tickets", "購票",
            "立即訂票", "立即订票", "優先訂票", "优先订票",
            "Book Now", "Get Tickets", "Purchase",
        ]
        try:
            content = await self.page.content()
            for kw in buy_keywords:
                if kw.lower() in content.lower():
                    return True
        except Exception:
            pass
        return False

    async def checkout(self) -> bool:
        """
        快速结账流程:
          选择日期 → 选择票价档位 → 选择数量 → 加入购物车 → 结账
        """
        logger.info("🛒 开始快速选票结账...")
        tkt = self.config.ticket

        try:
            # 1. 选择日期 (如果有多场)
            if tkt.preferred_date:
                await self._select_date(tkt.preferred_date)
            else:
                # 不指定日期就选第一个可用的
                await self._select_first_available_date()

            # 2. 选择票价档位
            selected = False
            for tier in tkt.price_tiers:
                if await self._select_price_tier(tier):
                    selected = True
                    logger.info(f"✅ 已选择票价: {tier}")
                    break

            if not selected:
                logger.error("❌ 所有目标票价档位均不可用")
                return False

            # 3. 选择数量
            await self._select_quantity(tkt.quantity)

            # 4. 点击下一步/加入购物车
            await self._click_next()

            # 5. 确认订单页面 — 检查是否有验证
            await asyncio.sleep(1)
            if await self._detect_captcha():
                await self._notify_captcha()
                await self._wait_for_captcha_solve()

            # 6. 尝试自动填充支付信息 (如果配置了)
            if self.config.account.card_number:
                await self._fill_payment()

            # 7. 最终需要用户确认支付
            await self._notify_final_confirm()

            logger.info("🎉 选票流程完成! 请在浏览器中完成支付。")
            return True

        except Exception as e:
            logger.error(f"结账过程出错: {e}")
            return False

    async def _select_date(self, date: str) -> None:
        """选择演出日期"""
        logger.info(f"📅 选择日期: {date}")
        try:
            # 尝试点击包含日期的按钮/链接
            date_selectors = [
                f'button:has-text("{date}")',
                f'a:has-text("{date}")',
                f'[value*="{date}"]',
                f'option:has-text("{date}")',
            ]
            for sel in date_selectors:
                try:
                    elem = await self.page.wait_for_selector(sel, timeout=3000)
                    if elem:
                        await elem.click()
                        await asyncio.sleep(1)
                        return
                except PlaywrightTimeout:
                    continue
            logger.warning(f"找不到日期选择: {date}, 跳过")
        except Exception as e:
            logger.warning(f"选择日期失败: {e}")

    async def _select_first_available_date(self) -> None:
        """选择第一个可用的日期"""
        logger.info("📅 自动选择首个可用日期...")
        # 很多售票页面会列出所有日期, 点击第一个"购买"按钮即可

    async def _select_price_tier(self, tier: str) -> bool:
        """选择票价档位, 返回是否成功"""
        logger.info(f"💵 尝试选择票价: {tier}")
        try:
            # 查找包含该票价的行, 点击其旁边的选择按钮
            # 去掉 HKD 前缀用于匹配
            price_keywords = tier.replace("HKD", "").strip()

            selectors = [
                f'text="{tier}"',
                f'text="{price_keywords}"',
                f'[value*="{price_keywords}"]',
                f'option:has-text("{price_keywords}")',
                f'label:has-text("{price_keywords}")',
            ]

            for sel in selectors:
                try:
                    elem = await self.page.wait_for_selector(sel, timeout=2000)
                    if elem:
                        # 点击票价行或其父级选择按钮
                        await elem.click()
                        await asyncio.sleep(0.5)
                        return True
                except PlaywrightTimeout:
                    continue

            return False
        except Exception:
            return False

    async def _select_quantity(self, quantity: int) -> None:
        """选择购票数量"""
        logger.info(f"🔢 选择数量: {quantity}")
        try:
            qty_str = str(quantity)
            selectors = [
                f'select:has(option[value="{qty_str}"])',
                f'input[type="number"]',
                f'[name*="qty"]',
                f'[name*="quantity"]',
                f'select:has-text("數量")',
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

            # 备选: 查找数字按钮点击
            qty_btn = await self.page.query_selector(f'button:has-text("{qty_str}")')
            if qty_btn:
                await qty_btn.click()
        except Exception as e:
            logger.warning(f"设置数量失败: {e}")

    async def _click_next(self) -> None:
        """点击下一步/结账按钮"""
        next_keywords = [
            "下一步", "繼續", "继续", "Next", "Continue",
            "結賬", "结账", "Checkout", "Proceed",
            "加入購物車", "加入购物车", "Add to Cart",
        ]
        for kw in next_keywords:
            try:
                btn = await self.page.wait_for_selector(
                    f'button:has-text("{kw}"), a:has-text("{kw}"), input[value*="{kw}"]',
                    timeout=2000,
                )
                if btn:
                    await btn.click()
                    logger.info(f"👉 点击了: {kw}")
                    await asyncio.sleep(2)
                    return
            except PlaywrightTimeout:
                continue

    async def _fill_payment(self) -> None:
        """尝试自动填充信用卡信息"""
        logger.info("💳 填充支付信息...")
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
                    logger.info(f"  填充: {selector}")
            except Exception:
                pass

    async def _notify_final_confirm(self) -> None:
        """通知用户最后确认支付"""
        logger.warning("=" * 50)
        logger.warning("🛎️  请在浏览器中确认订单并完成支付!")
        logger.warning("=" * 50)

        desktop_notify("抢票助手 - 请确认", "订单已准备好，请尽快确认支付!")
        if self.config.bot.sound_alert:
            self.sound_proc = play_alert_sound(repeat=True, interval=3)
            # 60秒后自动停止
            await asyncio.sleep(60)
            stop_alert(self.sound_proc)

    async def run(self, event_url: str, sale_time: datetime) -> bool:
        """主流程"""
        try:
            await self.setup()

            # 登录
            logged_in = await self.login()
            if not logged_in:
                logger.error("登录失败")

            # 计算等待时间
            now = datetime.now()
            wait_seconds = (sale_time - now).total_seconds()

            if wait_seconds > 0:
                logger.info(f"⏳ 距开售还有 {int(wait_seconds)} 秒, 启动监控...")
                if wait_seconds > 60:
                    countdown(int(wait_seconds - 50), "距开售")

            # 监控页面直到购票按钮出现
            success = await self.monitor_event_page(event_url, sale_time)
            if not success:
                logger.error("未能进入购票页面")
                return False

            # 快速结账
            checkout_ok = await self.checkout()
            return checkout_ok

        except Exception as e:
            logger.error(f"运行出错: {e}", exc_info=True)
            return False
        finally:
            # 保持浏览器开启，让用户手动操作
            stop_alert(self.sound_proc)
            logger.info("脚本主流程结束，浏览器保持开启供手动操作...")

    async def cleanup(self) -> None:
        """清理资源"""
        stop_alert(self.sound_proc)
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
