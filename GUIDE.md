# The Weeknd 香港演唱会抢票 — 操作指南

## 1. 安装（一次性）

```bash
pip3 install playwright
python3 -m playwright install chromium
```

Windows 用户用 `pip` / `python` 代替。

## 2. 获取脚本

把整个 `first-cc` 文件夹发过去。或通过 git clone。

## 3. 登录（一次性）

把 `cookies/hkticketing_chromium.json` 文件发给朋友，放到 `cookies/` 目录下，无需他登录。

没有 cookie 的话，首次运行时会弹出浏览器让他登录你的账户：

```bash
python3 run.py --phase livenation --time "2026-05-20 14:00:00" --dry-run --browsers 1
```

## 4. 配置

`config.py` 中已设好：日期 `10-31`、票价 `$1108→$908→$808`、数量 `2` 张。可按需修改。

## 5. 抢票命令

| 场次 | 日期 | 命令 |
|------|------|------|
| 艺人优先购 | 5/18 10:00 | `python3 run.py --phase artist --time "2026-05-18 10:00:00" --url "活动URL"` |
| Live Nation 优先购 | 5/20 14:00 | `python3 run.py --phase livenation --time "2026-05-20 14:00:00"` |
| 公开发售 | 5/21 10:00 | `python3 run.py --phase general --time "2026-05-21 10:00:00" --url "活动URL"` |

> 艺人优先购和公开发售的 HK Ticketing 活动 URL 尚未公布，拿到后通过 `--url` 传入。

开 3 个浏览器窗口提高成功率：`--browsers 3`

## 6. 过程说明

脚本自动处理排队和选票结账。**朋友只需做两件事：**
1. 出现验证码时点一下（10 秒）
2. 最后确认支付

## 7. 常见问题

**浏览器打不开 (SingletonLock)：**
```bash
pkill -f "Google Chrome for Testing" && rm -f browser_data/chromium/SingletonLock
```

**Trip.com 优先购：** 仅限手机 App，网页端无法购买。

**没有 Cookie 文件：** 首次运行会自动弹出浏览器让登录。
