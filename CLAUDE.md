# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

跨平台 DeepSeek API 余额监控工具：托盘图标显示余额、余额不足告警、历史记录查看器、忙时消耗速率估算。**本仓库（`legacy` 分支）只维护 Python 版。**

原 Rust 1.x 的 Windows/Linux 实现（`rust-windows/`、`rust-linux/`）与 Rainmeter / Plasma 6 小组件**已停止维护**；需要 Rust 版本请使用 **Rust 2.x**：<https://github.com/wenyinos/DeepSeekBalanceMonitor/releases/latest>。

## 常用命令

### Python 版（Windows / macOS）

```bash
pip install -r requirements.txt
python main.py                          # 运行托盘应用（src/ 为运行时，main.py 仅入口）
python -m unittest discover -s tests -v # 全部测试（与 CI 一致）
python scripts/test_api.py YOUR_API_KEY # 真实 API 连接验证
scripts\build_exe.bat                   # Windows 单文件 EXE
cd src/mac && bash ../scripts/build_mac.sh   # macOS 应用
```

- 运行单个测试文件：`python -m unittest discover -s tests -p test_core.py`
- 测试文件无 `__main__` 入口，不能直接 `python tests/test_core.py`

## 高层架构

### 多平台实现矩阵

| 平台 | 路径 | 技术栈 |
|---|---|---|
| Python Windows | `src/`, `main.py` | pystray + Tkinter，Windows 10+ |
| Python macOS | `src/mac/`, `src/webview/` | rumps + pywebview，macOS 10.14+ |

### Python 核心模块（Windows）

- `src/config.py`: 常量、i18n (`_T` 字典)、配置加载/保存、DPI 感知
- `src/api_client.py`: 余额查询、服务状态检查、代理
- `src/tray_app.py`: 托盘主循环、通知、菜单、余额调度
- `src/app_state.py`: 共享状态（余额、配置、运行状态）
- `src/icon_renderer.py`: 动态托盘图标（Pillow）
- `src/settings_dialog.py` / `src/history_dialog.py`: 设置窗口 / 历史查看器
- `src/storage.py`: SQLite、忙时切片消耗速率算法
- `src/secure_settings.py`: Fernet + SQLite 加密存储 API Key
- `src/rainmeter_server.py`: Rainmeter 本地 HTTP 接口（已停止维护）

### macOS 实现（两个设置界面并存）

- `src/mac/main.py`: rumps 托盘应用
- `src/mac/keystore.py`: Fernet/Keychain 加密 API Key
- `src/webview/`: pywebview 设置窗口，由托盘应用以**子进程**启动（`python -m src.webview.main`），`bridge.py` 的 JsApi 与 Python 通信，用 `CONFIG_DIR/.settings_changed` 哨兵文件通知主进程
- `src/mac/settings.py`: tkinter 回退设置窗口

### 历史实现（已停止维护）

- Rust 1.x：`rust-linux/`、`rust-windows/`，不再开发，也不再提供下载与构建支持。
- Rainmeter（Windows）与 Plasma 6（Linux）小组件：不再维护。
- 需要 Rust 版本请使用 Rust 2.x：<https://github.com/wenyinos/DeepSeekBalanceMonitor/releases/latest>。

## 核心约定

### 配置与密钥存储

- 配置文件位置：Windows `%APPDATA%\DeepSeek Balance Monitor\config.json`；Linux `~/.config/deepseek-balance-monitor/config.json`；macOS `~/Library/Application Support/DeepSeek Balance Monitor/config.json`
- **API Key 永不写入 config.json**，使用加密存储（Python: Fernet + SQLite；macOS: Keychain/Fernet）

### i18n

- Python 版所有 UI 文案集中在 `src/core/config.py` 的 `_T` 字典，新增文案必须加进去，不要硬编码

### 忙时消耗速率算法（v1.2.7+）

- 忙时切片算法替代原有充值跳变检测：识别忙时区间（排除闲时/平直段），返回**忙时小时消耗速率**（CNY/小时）与预计可用忙时小时数
- 调用 `get_consumption_rate()` 注意返回值语义：`hourly_rate` 而非旧 `daily_rate`
- 显示格式统一——中文 `📊 忙时消耗 0.06/小时 | 预计可用 28 天 4 小时`；英文 `📊 Busy: 0.06/hr | Est. 28d 4h remaining`
- **样本时长门槛（v2.4.0）**：参与加权的区间必须不短于 `max(60 秒, 半个轮询周期)`，替代原先 0.01 小时（36 秒）的经验值——46 秒区间携带 0.08 落差时会独占权重、外推出 6.26/小时

### 余额与统计口径（Python v2.4.0）

- Python 版当前版本 **v2.4.0**：应用内显示于设置页作者块上方；exe 版本资源见 `scripts/version_info.txt`
- **负分量不是可用余额**：DeepSeek 各分量各自钳 0，`total_balance` 由钳后分量重算（`充值 -0.10 + 赠送 6.00` → **6.00**，而非 API 原始相加 5.90）；历史负分量行在 `storage._connect()` 幂等修正（`WHERE topped<0 OR granted<0`）
- **统计读 `total`，不读 `topped`**：消耗可能走赠送余额，只读充值列会得到恒定序列（实测速率恒 0、预计可用算出负值）；预计可用基数 `max(0, 最新 total)`
- 注意 `total = 充值 + 赠送` 并非所有平台成立（OpenRouter 的 `topped_up_balance` 是累计充值而非剩余现金），故不得对全部历史行按分量重算

### 图标颜色状态

| 颜色 | 含义 |
|---|---|
| Teal | 余额正常 |
| Red | 余额不足或 API 错误 |
| Warm Gray | API 服务降级 |
| Gray | 尚未查询或未配置 Key |

### API 端点与代理

- `api.deepseek.com/user/balance` — 余额查询
- `status.deepseek.com` — DeepSeek 服务状态（FlashDuty 托管，RSC 解析）；**双源**：该规范域名优先，失败回退 FlashDuty 后端主机 `cn.statuspage.flashduty.com/deepseek`。⚠️ 早期使用的 `status.flashcat.cloud/deepseek` 是 **FlashDuty 自家**状态页（302 到根、无 DeepSeek 数据），已弃用；旧接口 `status.deepseek.com/api/v2` 亦已弃用
- 代理：`http_proxy` 配置项 + `proxy_enabled` 开关；禁用时保留代理地址不清除

### 版本工具链

- Python 版发布：tag `v*` 触发 GitHub Actions 构建。

## 注意事项

- 本仓库只改 Python 实现，不再同步 Rust 1.x。
- Python 版 tkinter + pystray 双事件循环，改动时注意避免死锁
- macOS 构建脚本在 `src/mac` 下运行；改动 macOS 相关文件时遵循现有目录约束
- **单实例**：Python 版二次启动被拒（Windows 命名互斥体 / 其它平台 flock），提示后退出；`scripts/build_exe.bat` 会等旧进程真正退出再启动新构建，否则新 exe 会被锁拒绝而留下旧版在托盘里
- **SQLite**：连接时启用 WAL 并带 `(api_id, timestamp)`、`timestamp` 索引；busy timeout 无需自行设置（Python `sqlite3.connect()` 默认 5 s）
- **首次打开主界面：Tk 预热与绘制约束**：`tray_app.main()` 启动时预热两件事——首个带 emoji 的 `ttk.Button`（Windows 上 0.6–0.9 s，emoji 字体回退）与一个 `-alpha 0` 的不可见窗口（进程内首个 Toplevel 首帧 0.2–0.3 s）。看板侧另有三条：画布 `<Configure>` 会先以 1×1 触发（尺寸未就绪勿绘）、画布图元数量即绘制成本（折线圆点已等比抽样 ≤48）、三个图表区块每空闲 tick 建一个且主窗先映射再构建 tab
