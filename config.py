"""
快达票 HK Ticketing 抢票配置文件
使用前请根据实际情况修改以下配置
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class SalePhase(Enum):
    """抢票阶段"""
    ARTIST_PRESALE = "artist_presale"       # 5/18 艺人官网优先
    LIVE_NATION = "live_nation_presale"      # 5/20 Live Nation 会员优先
    GENERAL_SALE = "general_sale"            # 5/21 公开发售
    TRIP_COM = "trip_com_presale"            # 5/20 Trip.com 优先


# ============================================================
#  演唱会信息（实际 URL 待官方公布后更新）
# ============================================================

# The Weeknd 香港演唱会 2026
# 日期: 2026年10月30-31日, 地点: 启德体育园
# 票价: 待公布 (预计 HKD 680 / 980 / 1280 / 1680 / 2080)

EVENT_URLS = {
    SalePhase.ARTIST_PRESALE: "https://www.hkticketing.com/events/the-weeknd-2026",  # 待官方公布后替换
    SalePhase.LIVE_NATION: "https://www.hkticketing.com/events/the-weeknd-2026-ln",   # 待官方公布后替换
    SalePhase.GENERAL_SALE: "https://www.hkticketing.com/events/the-weeknd-2026",     # 待官方公布后替换
}


@dataclass
class TicketConfig:
    """你的购票偏好"""
    # 目标日期: 10月30日 或 10月31日, 设为 None 表示哪场都行
    preferred_date: Optional[str] = None  # "10-30" 或 "10-31" 或 None

    # 目标票价档位 (按优先级排列, 第一个没票就试下一个)
    # 价格 HKD, 待官方公布后调整
    price_tiers: List[str] = field(default_factory=lambda: [
        "HKD 1280",
        "HKD 980",
        "HKD 1680",
        "HKD 680",
        "HKD 2080",
    ])

    # 购票数量 (快达票每账户限 6 张)
    quantity: int = 2

    # 座位偏好: "any" / "front" / "middle" / "rear"
    seat_preference: str = "any"


@dataclass
class AccountConfig:
    """快达票账户信息"""
    email: str = ""
    password: str = ""

    # 支付信息 (建议用 AE 卡, 免短信验证更快)
    card_number: str = ""
    card_expiry_month: str = ""
    card_expiry_year: str = ""
    card_cvv: str = ""
    card_holder_name: str = ""


@dataclass
class BotConfig:
    """抢票机器人配置"""
    # 在开售前多少秒开始监控 (提前进入等待队列)
    warmup_seconds: int = 300  # 5分钟

    # 页面刷新间隔 (秒)
    poll_interval: float = 1.0

    # 同时开几个浏览器窗口 (更多窗口 = 更多排队位置, 但需要不同浏览器)
    concurrent_browsers: int = 2

    # 浏览器类型列表 (不同浏览器获得独立排队位)
    browser_types: List[str] = field(default_factory=lambda: ["chromium", "firefox"])

    # 是否显示浏览器窗口 (False = 无头模式, True = 可见)
    headless: bool = False

    # 是否播放声音提醒
    sound_alert: bool = True

    # 声音重复间隔 (秒)
    sound_repeat: int = 5

    # 是否发送系统通知
    desktop_notification: bool = True

    # cookie 保存路径 (免重复登录)
    cookie_dir: str = "./cookies"

    # 日志级别
    log_level: str = "INFO"


@dataclass
class Config:
    ticket: TicketConfig = field(default_factory=TicketConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    sale_phase: SalePhase = SalePhase.GENERAL_SALE


# 默认配置实例
config = Config()
