#!/usr/bin/env python3
"""
快达票半自动抢票助手 — 启动入口

用法:
  # 公开发售 (5/21 10:00)
  python run.py --phase general --time "2026-05-21 10:00:00"

  # 艺人优先购 (5/18 10:00)
  python run.py --phase artist --time "2026-05-18 10:00:00"

  # Live Nation 优先购 (5/20 14:00)
  python run.py --phase livenation --time "2026-05-20 14:00:00"

  # 测试模式 (不实际购买)
  python run.py --phase general --time "2026-05-21 10:00:00" --dry-run

  # 无头模式 (后台运行, 不显示浏览器窗口)
  python run.py --phase general --time "2026-05-21 10:00:00" --headless

  # 指定并发浏览器数
  python run.py --phase general --time "2026-05-21 10:00:00" --browsers 3
"""
import asyncio
import argparse
import sys
from datetime import datetime

from config import Config, SalePhase, TicketConfig
from bot import HKTicketingBot
from utils import setup_logging, logger, desktop_notify


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="快达票 HK Ticketing 半自动抢票助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py --phase general --time "2026-05-21 10:00:00"
  python run.py --phase livenation --time "2026-05-20 14:00:00" --browsers 2
  python run.py --phase artist --time "2026-05-18 10:00:00" --tier "HKD 1280" --qty 2
        """,
    )

    parser.add_argument(
        "--phase",
        type=str,
        required=True,
        choices=["artist", "livenation", "general", "trip"],
        help="抢票阶段: artist=艺人优先, livenation=Live Nation会员, general=公开发售, trip=Trip.com",
    )
    parser.add_argument(
        "--time",
        type=str,
        required=True,
        help='开售时间 (香港时间), 格式: "2026-05-21 10:00:00"',
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="活动页面 URL (留空则使用配置文件中的默认URL)",
    )
    parser.add_argument(
        "--tier",
        type=str,
        default=None,
        help='首选票价, 如 "HKD 1280" (默认尝试多个档位)',
    )
    parser.add_argument(
        "--qty",
        type=int,
        default=None,
        help="购票数量 (默认 2 张, 最多 6 张)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help='目标日期: "10-30" 或 "10-31" (默认不限)',
    )
    parser.add_argument(
        "--browsers",
        type=int,
        default=None,
        help="并发浏览器窗口数 (默认 2, 不同浏览器获得独立排队位)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式 (不显示浏览器窗口)",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="禁用声音提醒",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="禁用系统通知",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="测试模式 (不进行实际购买操作)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )

    return parser.parse_args()


def build_config(args: argparse.Namespace) -> Config:
    """根据命令行参数构建配置"""
    config = Config()

    # 设置抢票阶段
    phase_map = {
        "artist": SalePhase.ARTIST_PRESALE,
        "livenation": SalePhase.LIVE_NATION,
        "general": SalePhase.GENERAL_SALE,
        "trip": SalePhase.TRIP_COM,
    }
    config.sale_phase = phase_map[args.phase]

    # 用户偏好
    if args.tier:
        config.ticket.price_tiers = [args.tier]
    if args.qty:
        config.ticket.quantity = min(args.qty, 6)
    if args.date:
        config.ticket.preferred_date = args.date

    # 机器人配置
    if args.browsers:
        config.bot.concurrent_browsers = args.browsers
    if args.headless:
        config.bot.headless = True
    if args.no_sound:
        config.bot.sound_alert = False
    if args.no_notify:
        config.bot.desktop_notification = False

    return config


def get_event_url(config: Config, args: argparse.Namespace) -> str:
    """获取活动页面 URL"""
    from config import EVENT_URLS

    if args.url:
        return args.url
    return EVENT_URLS.get(config.sale_phase, "")


async def run_single_bot(config: Config, event_url: str, sale_time: datetime, browser_name: str, dry_run: bool) -> None:
    """运行单个浏览器实例的抢票机器人"""
    bot = HKTicketingBot(config, browser_name=browser_name)

    try:
        if dry_run:
            logger.info(f"🧪 [{browser_name}] 测试模式: 仅启动浏览器, 不进行实际购买")
            await bot.setup()
            await bot.login()
            logger.info("测试完成, 浏览器保持开启120秒供检查...")
            await asyncio.sleep(120)
        else:
            success = await bot.run(event_url, sale_time)
            if success:
                logger.info(f"🎉 [{browser_name}] 成功进入结账流程!")
            else:
                logger.error(f"❌ [{browser_name}] 抢票失败")
    except Exception as e:
        logger.error(f"[{browser_name}] 异常: {e}", exc_info=True)
    finally:
        # 不主动关闭浏览器, 让用户有机会手动操作
        logger.info(f"[{browser_name}] 浏览器保持开启...")


async def main() -> None:
    args = parse_args()
    config = build_config(args)

    # 设置日志
    setup_logging(args.log_level)

    # 解析开售时间
    try:
        sale_time = datetime.strptime(args.time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.error('时间格式错误, 请使用: "YYYY-MM-DD HH:MM:SS"')
        sys.exit(1)

    event_url = get_event_url(config, args)
    if not event_url:
        logger.error(
            "未设置活动 URL! 请使用 --url 参数指定, "
            "或在 config.py 的 EVENT_URLS 中配置"
        )
        sys.exit(1)

    # 打印配置摘要
    logger.info("=" * 60)
    logger.info("  快达票半自动抢票助手")
    logger.info("=" * 60)
    logger.info(f"  阶段: {config.sale_phase.value}")
    logger.info(f"  开售: {args.time} HKT")
    logger.info(f"  票价: {', '.join(config.ticket.price_tiers)}")
    logger.info(f"  数量: {config.ticket.quantity} 张")
    logger.info(f"  日期: {config.ticket.preferred_date or '不限'}")
    logger.info(f"  并发: {config.bot.concurrent_browsers} 个浏览器")
    logger.info(f"  模式: {'测试' if args.dry_run else '实战'}")
    logger.info(f"  URL: {event_url}")
    logger.info("=" * 60)

    # 检查时间是否已过
    now = datetime.now()
    if sale_time < now:
        logger.warning("⚠️ 指定的开售时间已过! 将立即开始尝试。")

    # 启动多个浏览器实例
    browser_types = config.bot.browser_types[: config.bot.concurrent_browsers]
    # 如果并发数大于配置的浏览器类型数, 循环使用
    while len(browser_types) < config.bot.concurrent_browsers:
        browser_types.append("chromium")

    logger.info(f"🚀 启动 {len(browser_types)} 个浏览器实例: {browser_types}")

    # 并发运行
    tasks = [
        run_single_bot(config, event_url, sale_time, bt, args.dry_run)
        for bt in browser_types
    ]
    await asyncio.gather(*tasks)

    # 发送启动通知
    desktop_notify("抢票助手已启动", f"将在 {args.time} 开始抢票, {len(browser_types)} 个窗口就绪")

    logger.info("\n所有实例已启动, 等待中...")
    logger.info("提示: reCAPTCHA 出现时会自动提醒, 请留意系统通知和声音!")


if __name__ == "__main__":
    asyncio.run(main())
