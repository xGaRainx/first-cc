"""
工具函数：系统通知、声音提醒、日志、Cookie 管理
"""
import os
import json
import logging
import subprocess
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("ticket_bot")


def setup_logging(level: str = "INFO") -> None:
    """配置日志"""
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.addHandler(handler)

    # 同时写入文件
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)
    fh = logging.FileHandler(
        log_dir / f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def desktop_notify(title: str, message: str) -> None:
    """发送 macOS 系统通知"""
    try:
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}" sound name "Ping"'
        ], check=False, timeout=3)
        logger.info(f"📬 已发送系统通知: {title}")
    except Exception as e:
        logger.warning(f"发送通知失败: {e}")


def play_alert_sound(repeat: bool = False, interval: int = 5) -> Optional[subprocess.Popen]:
    """播放提醒声音 (macOS 系统提示音)"""
    script = """
    on run
        repeat
            beep 3
            delay {}
        end repeat
    end run
    """.format(interval)

    try:
        if repeat:
            proc = subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return proc
        else:
            subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"], check=False, timeout=3)
    except Exception as e:
        logger.warning(f"播放声音失败: {e}")
    return None


def stop_alert(proc: Optional[subprocess.Popen]) -> None:
    """停止重复声音提醒"""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


async def save_cookies(context, name: str, cookie_dir: str = "./cookies") -> None:
    """保存浏览器 cookie 到文件"""
    path = Path(cookie_dir)
    path.mkdir(exist_ok=True)
    cookies = await context.cookies()
    filepath = path / f"{name}.json"
    with open(filepath, "w") as f:
        json.dump(cookies, f)
    logger.info(f"💾 Cookie 已保存: {filepath}")


async def load_cookies(context, name: str, cookie_dir: str = "./cookies") -> bool:
    """从文件加载 cookie 到浏览器上下文"""
    filepath = Path(cookie_dir) / f"{name}.json"
    if not filepath.exists():
        logger.info(f"未找到 Cookie 文件: {filepath}")
        return False
    try:
        with open(filepath) as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        logger.info(f"✅ Cookie 已加载: {filepath}")
        return True
    except Exception as e:
        logger.warning(f"加载 Cookie 失败: {e}")
        return False


def countdown(seconds: int, label: str = "距离开售") -> None:
    """倒计时日志输出"""
    for remaining in range(seconds, 0, -1):
        mins, secs = divmod(remaining, 60)
        print(f"\r⏳ {label}: {mins:02d}:{secs:02d}", end="", flush=True)
        time.sleep(1)
    print()
