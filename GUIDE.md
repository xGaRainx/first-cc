# The Weeknd 香港演唱会抢票 — 操作指南

## 你的朋友需要做什么

整个流程只需 **10 分钟** 配置一次，之后每次抢票只需一行命令。

---

## 1. 安装环境（一次性）

### macOS
```bash
pip3 install playwright
python3 -m playwright install chromium
```

### Windows
```bash
pip install playwright
python -m playwright install chromium
```

> Python 需提前安装：python.org 下载，安装时勾选「Add Python to PATH」

---

## 2. 获取脚本

把整个项目文件夹 `first-cc` 发给你朋友（U盘/AirDrop/网盘均可），放在任意目录下。

如果会用 git：
```bash
git clone https://github.com/xGaRainx/first-cc.git
cd first-cc
```

---

## 3. 登录快达票（一次性）

### 方案 A：你把自己的 Cookie 发给他（推荐，免登录）

你把 `cookies/hkticketing_chromium.json` 文件发给他，放到项目 `cookies/` 目录下。

### 方案 B：他本地登录

首次运行时脚本会自动弹出浏览器，让他登录你的快达票账户：

```bash
cd first-cc
python3 run.py --phase livenation --time "2026-05-20 14:00:00" --dry-run --browsers 1
```

浏览器弹出后 → 点「登入」→ 输入账号密码 → 登录成功会自动保存 Cookie。

登录完成后可以关掉浏览器窗口，或等 2 分钟自动关闭。

---

## 4. 修改配置（发给他之前你改好）

在 `config.py` 中确认以下配置（当前已设好）：
- **日期**：`10-31`（10月31日）
- **票价**：`$1108 → $908 → $808`（高到低）
- **数量**：`2` 张
- **账户**：可以填入你的快达票账号密码作为备忘

如果需要修改票价优先级，编辑 `config.py` 第 49-53 行：
```python
price_tiers: List[str] = field(default_factory=lambda: [
    "HKD 1108",
    "HKD 908",
    "HKD 808",
])
```

---

## 5. 抢票命令

| 场次 | 日期 & 时间 | 命令 |
|------|------------|------|
| 艺人优先购 | 5/18 10:00 | `python3 run.py --phase artist --time "2026-05-18 10:00:00" --url "快达票活动URL"` |
| Trip.com 优先购 | 5/20 10:00 | Trip.com 仅限 App，需要在手机上操作 |
| Live Nation 优先购 | 5/20 14:00 | `python3 run.py --phase livenation --time "2026-05-20 14:00:00"` |
| 公开发售 | 5/21 10:00 | `python3 run.py --phase general --time "2026-05-21 10:00:00" --url "快达票活动URL"` |

> **注意**：艺人优先购和公开发售的快达票活动页 URL 尚未公布，届时你拿到后把 URL 发给朋友，用 `--url` 参数传入。

### 推荐：开 3 个浏览器窗口提高成功率

```bash
python3 run.py --phase livenation --time "2026-05-20 14:00:00" --browsers 3
```

---

## 6. 抢票过程会发生什么

```
开售前5分钟 → 朋友运行命令 → 浏览器自动打开
     ↓
脚本自动监控活动页面 → 如果排队（Queue-it）自动等
     ↓
出现机器人验证（reCAPTCHA）→ 电脑发出声音 + 弹通知 → 朋友点一下验证框（10秒）
     ↓
验证通过 → 脚本自动：选日期 → 选票价 → 选数量 → 下单
     ↓
最终确认页面 → 再次提醒 → 朋友确认支付
```

**朋友只需要做两件事：**
1. 出现验证码时点一下（约 10 秒）
2. 最后确认支付

其余全自动。

---

## 7. 抢票当天 checklist

- [ ] 提前 10 分钟打开终端
- [ ] 先用 `--dry-run` 跑一次确认 Cookie 有效
- [ ] 开售前 5 分钟运行正式命令
- [ ] 确保网络稳定（建议 WiFi + 手机热点双保险）
- [ ] 电脑音量打开（验证码提醒用）
- [ ] 信用卡在手边（可能需要输入 CVV）

---

## 8. 常见问题

**Q: 浏览器打不开，报 SingletonLock 错误？**
```bash
pkill -f "Google Chrome for Testing"
rm -f browser_data/chromium/SingletonLock
```

**Q: 识别不了登录状态？**
检查 `bot.py` 中的 `HK_LOGIN_INDICATOR` 选择器是否正确（当前为 `div.title___UIF7d`）。

**Q: Trip.com 怎么抢？**
Trip.com 优先购仅限手机 App，网页端无法购买。需要在手机上操作。

**Q: 可以多台电脑同时抢吗？**
可以，不同电脑/网络各自独立排队，互不影响，成功率更高。
