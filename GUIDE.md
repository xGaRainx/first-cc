# The Weeknd 香港演唱会抢票 — 操作指南

## 1. 安装（一次性）

```bash
pip3 install playwright
python3 -m playwright install chromium
```

Windows 用户用 `pip` / `python` 代替。

## 2. 获取脚本

将整个项目文件夹放到本地任意目录。或通过 git clone。

## 3. 登录快达票（一次性）

将 `cookies/hkticketing_chromium.json` 放到 `cookies/` 目录下，即可跳过登录。

如无此文件，首次运行时会弹出浏览器供手动登录：

```bash
python3 run.py --phase livenation --time "2026-05-20 14:00:00" --dry-run --browsers 1
```

登录成功后 Cookie 自动保存，后续无需再登。

## 4. 配置

`config.py` 中已设好：
- 日期：`10-31`
- 票价优先级：`$1108 → $908 → $808`
- 数量：`2` 张

可按需修改。

## 5. 抢票命令

| 场次 | 日期 | 命令 |
|------|------|------|
| 艺人优先购 | 5/18 10:00 | `python3 run.py --phase artist --time "2026-05-18 10:00:00" --url "活动URL"` |
| Live Nation 优先购 | 5/20 14:00 | `python3 run.py --phase livenation --time "2026-05-20 14:00:00"` |
| 公开发售 | 5/21 10:00 | `python3 run.py --phase general --time "2026-05-21 10:00:00" --url "活动URL"` |

> 艺人优先购和公开发售的 HK Ticketing 活动 URL 尚未公布，届时通过 `--url` 传入。

开 3 个浏览器窗口：`--browsers 3`

## 6. 过程说明

脚本自动处理排队和选票结账，仅需人工介入两次：
1. 出现验证码时点击验证（约 10 秒）
2. 最后确认支付

## 7. 常见问题

**浏览器打不开 (SingletonLock)：**
```bash
pkill -f "Google Chrome for Testing" && rm -f browser_data/chromium/SingletonLock
```

**Trip.com 优先购：** 仅限手机 App，网页端不可用。

**没有 Cookie 文件：** 首次运行会自动弹出浏览器供登录。
