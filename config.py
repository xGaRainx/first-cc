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
#  The Weeknd 香港演唱会 2026 — 实际票价已公布 (2026-05-13)
#  日期: 10月30-31日 20:15, 地点: 启德体育园主场馆
#  HK Ticketing 活动页 URL 预计 5/18 前上线, 届时更新
# ============================================================

# 实际票价 (9个档位)
# VIP: $5,998 | $5,208 | $3,408
# 普通: $2,008 | $1,708 | $1,408 | $1,108 | $908 | $808

EVENT_URLS = {
    # HK Ticketing 活动页 — 待官方公布后替换为实际 URL
    # 通常格式类似: https://premier.hkticketing.com/shows/show.aspx?sh=XXXX
    # 也可直接搜索: https://www.hkticketing.com 搜 "The Weeknd"
    SalePhase.ARTIST_PRESALE: "",
    SalePhase.LIVE_NATION: "https://www.livenation.hk/en/event/the-weeknd-after-hours-til-dawn-tour-hong-kong-tickets-edp1672828",
    SalePhase.GENERAL_SALE: "",
}

# Trip.com 优先购页面
TRIP_COM_EVENT_URL = "https://hk.trip.com/blog/the-weeknd-concert-hk"


@dataclass
class TicketConfig:
    """你的购票偏好"""
    # 目标日期: 只要10月31日
    preferred_date: Optional[str] = "10-31"  # "10-30" 或 "10-31" 或 None

    # 目标票价档位 (按优先级排列, 第一个没票就试下一个)
    # 预算原因只考虑 $1108 / $908 / $808 三档
    price_tiers: List[str] = field(default_factory=lambda: [
        "HKD 1108",
        "HKD 908",
        "HKD 808",
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
