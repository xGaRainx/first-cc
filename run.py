#!/usr/bin/env python3
"""快达票半自动抢票助手 — CLI 入口"""
import asyncio
import argparse
import sys
from datetime import datetime

from config import Config, SalePhase
from bot import HKTicketingBot
from utils import setup_logging, logger, desktop_notify


def parse_args():
    parser = argparse.ArgumentParser(description="快达票 HK Ticketing 半自动抢票助手")

    parser.add_argument("--phase", type=str, required=True,
                        choices=["artist", "livenation", "general", "trip"],
                        help="artist/livenation/general/trip")
    parser.add_argument("--time", type=str, required=True,
                        help='开售时间 (HKT), 格式 "2026-05-21 10:00:00"')
    parser.add_argument("--url", type=str, default=None,
                        help="活动页面 URL (留空用配置文件默认值)")
    parser.add_argument("--tier", type=str, default=None,
                        help='票价 (如 "HKD 1108", 默认按优先级尝试)')
    parser.add_argument("--qty", type=int, default=None,
                        help="数量 (默认2, 上限6)")
    parser.add_argument("--date", type=str, default=None,
                        help='日期 "10-30" 或 "10-31"')
    parser.add_argument("--browsers", type=int, default=None,
                        help="并发浏览器数 (默认2)")
    parser.add_argument("--headless", action="store_true",
                        help="无头模式")
    parser.add_argument("--no-sound", action="store_true",
                        help="禁用声音")
    parser.add_argument("--no-notify", action="store_true",
                        help="禁用通知")
    parser.add_argument("--dry-run", action="store_true",
                        help="测试模式 (不实际购买)")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    return parser.parse_args()


def build_config(args):
    config = Config()
    phase_map = {
        "artist": SalePhase.ARTIST_PRESALE,
        "livenation": SalePhase.LIVE_NATION,
        "general": SalePhase.GENERAL_SALE,
        "trip": SalePhase.TRIP_COM,
    }
    config.sale_phase = phase_map[args.phase]

    if args.tier:
        config.ticket.price_tiers = [args.tier]
    if args.qty:
        config.ticket.quantity = min(args.qty, 6)
    if args.date:
        config.ticket.preferred_date = args.date
    if args.browsers:
        config.bot.concurrent_browsers = args.browsers
    if args.headless:
        config.bot.headless = True
    if args.no_sound:
        config.bot.sound_alert = False
    if args.no_notify:
        config.bot.desktop_notification = False

    return config


def get_event_url(config, args):
    from config import EVENT_URLS, TRIP_COM_EVENT_URL

    if args.url:
        return args.url
    if config.sale_phase == SalePhase.TRIP_COM:
        return TRIP_COM_EVENT_URL

    url = EVENT_URLS.get(config.sale_phase, "")
    if not url:
        logger.error(
            f"活动 URL 未配置! 请用 --url 参数传入, 或更新 config.py\n"
            f"用法: python run.py --phase {args.phase} --time \"{args.time}\" --url \"实际URL\""
        )
        sys.exit(1)
    return url


async def run_single_bot(config, event_url, sale_time, browser_name, dry_run):
    bot = HKTicketingBot(config, browser_name=browser_name)
    try:
        if dry_run:
            logger.info(f"🧪 [{browser_name}] 测试模式")
            await bot.setup()
            await bot.login()
            logger.info("测试完成, 浏览器保持开启120秒...")
            await asyncio.sleep(120)
        else:
            success = await bot.run(event_url, sale_time)
            if success:
                logger.info(f"🎉 [{browser_name}] 进入结账流程")
            else:
                logger.error(f"❌ [{browser_name}] 抢票失败")
    except Exception as e:
        logger.error(f"[{browser_name}] 异常: {e}")
    finally:
        logger.info(f"[{browser_name}] 浏览器保持开启...")


async def main():
    args = parse_args()
    config = build_config(args)
    setup_logging(args.log_level)

    try:
        sale_time = datetime.strptime(args.time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.error('时间格式错误, 使用 "YYYY-MM-DD HH:MM:SS"')
        sys.exit(1)

    event_url = get_event_url(config, args)

    logger.info("=" * 50)
    logger.info(f"  阶段: {config.sale_phase.value} | 开售: {args.time} HKT")
    logger.info(f"  票价: {', '.join(config.ticket.price_tiers)} | 数量: {config.ticket.quantity} | 日期: {config.ticket.preferred_date or '不限'}")
    logger.info(f"  浏览器: {config.bot.concurrent_browsers} 个 | 模式: {'测试' if args.dry_run else '实战'}")
    logger.info("=" * 50)

    if sale_time < datetime.now():
        logger.warning("⚠️ 开售时间已过, 将立即开始尝试")

    browser_types = config.bot.browser_types[:config.bot.concurrent_browsers]
    while len(browser_types) < config.bot.concurrent_browsers:
        browser_types.append("chromium")

    tasks = [run_single_bot(config, event_url, sale_time, bt, args.dry_run) for bt in browser_types]
    await asyncio.gather(*tasks)

    desktop_notify("抢票助手已启动", f"{len(browser_types)} 个窗口就绪")
    logger.info("reCAPTCHA 出现时会自动提醒, 留意系统通知和声音")


if __name__ == "__main__":
    asyncio.run(main())
