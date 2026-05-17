from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class SalePhase(Enum):
    ARTIST_PRESALE = "artist_presale"
    LIVE_NATION = "live_nation_presale"
    GENERAL_SALE = "general_sale"
    TRIP_COM = "trip_com_presale"


EVENT_URLS = {
    SalePhase.ARTIST_PRESALE: "https://www.livenation.hk/event/the-weeknd-after-hours-til-dawn-tour-hong-kong-tickets-edp1672835",
    SalePhase.LIVE_NATION: "https://www.livenation.hk/en/event/the-weeknd-after-hours-til-dawn-tour-hong-kong-tickets-edp1672828",
    SalePhase.GENERAL_SALE: "",
}

TRIP_COM_EVENT_URL = "https://hk.trip.com/blog/the-weeknd-concert-hk"
ARTIST_PRESALE_CODE = "4HTDASIA"  # 艺人官网优先购验证码


@dataclass
class TicketConfig:
    preferred_date: Optional[str] = "10-31"
    price_tiers: List[str] = field(default_factory=lambda: [
        "HKD 1108",
        "HKD 908",
        "HKD 808",
    ])
    quantity: int = 2
    seat_preference: str = "any"
    presale_code: str = ARTIST_PRESALE_CODE


@dataclass
class AccountConfig:
    email: str = ""
    password: str = ""
    card_number: str = ""
    card_expiry_month: str = ""
    card_expiry_year: str = ""
    card_cvv: str = ""
    card_holder_name: str = ""


@dataclass
class BotConfig:
    warmup_seconds: int = 300
    poll_interval: float = 1.0
    concurrent_browsers: int = 2
    browser_types: List[str] = field(default_factory=lambda: ["chromium", "firefox"])
    headless: bool = False
    sound_alert: bool = True
    sound_repeat: int = 5
    desktop_notification: bool = True
    cookie_dir: str = "./cookies"
    log_level: str = "INFO"


@dataclass
class Config:
    ticket: TicketConfig = field(default_factory=TicketConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    sale_phase: SalePhase = SalePhase.GENERAL_SALE


config = Config()
