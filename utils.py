"""通知、声音、日志、Cookie 管理 (macOS / Windows)"""
import os
import sys
import json
import logging
import subprocess
import time
import platform
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("ticket_bot")
IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"


def setup_logging(level: str = "INFO"):
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.addHandler(handler)

    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)
    fh = logging.FileHandler(log_dir / f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def desktop_notify(title: str, message: str):
    try:
        if IS_MACOS:
            subprocess.run(["osascript", "-e",
                            f'display notification "{message}" with title "{title}" sound name "Ping"'],
                           check=False, timeout=3)
        elif IS_WINDOWS:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5, threaded=True)
    except Exception as e:
        logger.warning(f"通知失败: {e}")


def play_alert_sound(repeat: bool = False, interval: int = 5):
    try:
        if IS_MACOS:
            if repeat:
                script = f"on run\nrepeat\nbeep 3\ndelay {interval}\nend repeat\nend run"
                return subprocess.Popen(["osascript", "-e", script],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"], check=False, timeout=3)
        elif IS_WINDOWS:
            import winsound
            if repeat:
                import threading
                def _beep_loop():
                    while True:
                        winsound.Beep(1000, 300)
                        time.sleep(interval)
                threading.Thread(target=_beep_loop, daemon=True).start()
            else:
                winsound.Beep(1000, 500)
    except Exception:
        pass
    return None


def stop_alert(proc: Optional[subprocess.Popen]):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


async def save_cookies(context, name: str, cookie_dir: str = "./cookies"):
    path = Path(cookie_dir)
    path.mkdir(exist_ok=True)
    cookies = await context.cookies()
    with open(path / f"{name}.json", "w") as f:
        json.dump(cookies, f)
    logger.info(f"💾 Cookie 已保存: {name}")


async def load_cookies(context, name: str, cookie_dir: str = "./cookies"):
    filepath = Path(cookie_dir) / f"{name}.json"
    if not filepath.exists():
        return False
    try:
        with open(filepath) as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        logger.info(f"✅ Cookie 已加载: {name}")
        return True
    except Exception as e:
        logger.warning(f"加载 Cookie 失败: {e}")
        return False


def countdown(seconds: int, label: str = "距离开售"):
    for remaining in range(seconds, 0, -1):
        mins, secs = divmod(remaining, 60)
        print(f"\r⏳ {label}: {mins:02d}:{secs:02d}", end="", flush=True)
        time.sleep(1)
    print()
