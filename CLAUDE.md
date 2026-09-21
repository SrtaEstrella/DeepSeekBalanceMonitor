# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

跨平台 DeepSeek API 余额监控工具：托盘图标显示余额、余额不足告警、历史记录查看器、忙时消耗速率估算，附带 Rainmeter (Windows) 与 Plasma 6 (Linux) 桌面小组件。同一功能有 **Python 和 Rust 双实现**，改动逻辑时需注意多端同步。

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

### Rust 版（工具链固定 1.77.2，见「版本工具链」）

```bash
cd rust-linux && cargo +1.77.2 build --release --locked
sudo ./install.sh                       # 系统级二进制 + 用户级 Plasma 小组件

cd rust-windows && cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked

# 两个 crate 的 main.rs 均含 #[cfg(test)] 测试模块
cd rust-linux && cargo +1.77.2 test --locked
cd rust-linux && cargo +1.77.2 fmt --check   # CI 校验格式
```

### Linux CLI（安装后，`dsmon`）

```bash
dsmon check              # 查询余额
dsmon daemon             # 守护进程模式
dsmon set-key            # 设置 API Key
dsmon set <field> <value># 修改配置
dsmon history [days]     # 查看历史
dsmon history export [days] [currency|all] [path|-]  # 导出 CSV
dsmon widget-status      # 输出 Plasma 小组件 JSON
dsmon opencode-go        # 查询 OpenCode Go 额度
dsmon opencode-go set-key <api_key>   # 加密保存 API Key
```

## 高层架构

### 多平台实现矩阵

| 平台 | 路径 | 技术栈 |
|---|---|---|
| Python Windows | `src/`, `main.py` | pystray + Tkinter，Windows 10+ |
| Python macOS | `src/mac/`, `src/webview/` | rumps + pywebview，macOS 10.14+ |
| Rust Windows | `rust-windows/` | native-windows-gui，Windows 7+ |
| Rust Linux | `rust-linux/` | CLI + 守护进程 + Plasma 6 小组件 |

### Python 核心模块（Windows）

- `src/config.py`: 常量、i18n (`_T` 字典)、配置加载/保存、DPI 感知
- `src/api_client.py`: 余额查询、服务状态检查、代理
- `src/tray_app.py`: 托盘主循环、通知、菜单、余额调度
- `src/app_state.py`: 共享状态（余额、配置、运行状态）
- `src/icon_renderer.py`: 动态托盘图标（Pillow）
- `src/settings_dialog.py` / `src/history_dialog.py`: 设置窗口 / 历史查看器
- `src/storage.py`: SQLite、忙时切片消耗速率算法
- `src/secure_settings.py`: Fernet + SQLite 加密存储 API Key
- `src/rainmeter_server.py`: Rainmeter 本地 HTTP 接口

### macOS 实现（两个设置界面并存）

- `src/mac/main.py`: rumps 托盘应用
- `src/mac/keystore.py`: Fernet/Keychain 加密 API Key
- `src/webview/`: pywebview 设置窗口，由托盘应用以**子进程**启动（`python -m src.webview.main`），`bridge.py` 的 JsApi 与 Python 通信，用 `CONFIG_DIR/.settings_changed` 哨兵文件通知主进程
- `src/mac/settings.py`: tkinter 回退设置窗口

### Rust 实现

- `rust-linux/src/main.rs`: 单文件包含 CLI、守护进程、忙时切片算法与 Plasma 小组件数据，含 `#[cfg(test)]` 测试模块
- `rust-linux/src/demo.rs`: 演示模式数据生成（用 `demo` 作 API Key 触发）
- `rust-windows/src/main.rs`: 原生 Windows GUI，结构类似 rust-linux

### 桌面小组件

- **Rainmeter**（仅 Windows）: 从 `127.0.0.1:17654` 读取本地状态接口，不直接持有 API Key。皮肤在 `rainmeter-widget/DeepSeekBalanceMonitor/`，支持中英文与高清（`.hd.ini`）变体
- **Plasma 6**（仅 Linux）: `rust-linux/plasmoid/` 的 C++ 小组件，通过 `dsmon widget-status` 取数；语言切换会写回 `dsmon` 的 `ui_language`

## 核心约定

### 配置与密钥存储

- 配置文件位置：Windows `%APPDATA%\DeepSeek Balance Monitor\config.json`；Linux `~/.config/deepseek-balance-monitor/config.json`；macOS `~/Library/Application Support/DeepSeek Balance Monitor/config.json`
- **API Key 永不写入 config.json**，使用加密存储（Python: Fernet + SQLite；macOS: Keychain/Fernet；Rust: SQLite `secure_settings`）

### i18n

- Python 版所有 UI 文案集中在 `src/config.py` 的 `_T` 字典，新增文案必须加进去，不要硬编码
- CLI（`dsmon`）输出固定英文，不随 `ui_language` 切换

### 忙时消耗速率算法（v1.2.7+）

- 忙时切片算法替代原有充值跳变检测：识别忙时区间（排除闲时/平直段），返回**忙时小时消耗速率**（CNY/小时）与预计可用忙时小时数
- 调用 `get_consumption_rate()` 注意返回值语义：`hourly_rate` 而非旧 `daily_rate`
- 显示格式统一——中文 `📊 忙时消耗 0.06/小时 | 预计可用 28 天 4 小时`；英文 `📊 Busy: 0.06/hr | Est. 28d 4h remaining`
- Rainmeter 取 `estimated_line` 字段；Plasma 直接从 `consumption_rate` 计算；Rust 版已跟进此算法

### 图标颜色状态

| 颜色 | 含义 |
|---|---|
| Teal | 余额正常 |
| Red | 余额不足或 API 错误 |
| Warm Gray | API 服务降级 |
| Gray | 尚未查询或未配置 Key |

### Opencode Go 额度（两 Rust 平台）

- 调用官方 API `GET https://opencode.ai/zen/go/v1/usage`（请求头 `Authorization: Bearer <api_key>`），返回 **5h 滚动 / 每周 / 每月** 三档用量的已用百分比（`percent`）与重置时间戳（`resetsAt`，ISO 8601，转换为剩余秒数展示）
- 凭据为单个 API Key（`sk-xxxxx`，从 https://opencode.ai/auth 获取），**加密存入 `secure_settings` 表**（独立 key `opencode_go_api_key`，与 DeepSeek API Key 同一加密机制），**不写入 config.json**
- 入口：rust-windows 设置窗口的「订阅」页（左侧导航依次是账号 / 常规 / 历史 / 订阅，订阅页含 OpenCode Go 与 Command Code 两组）与 Plasma 小组件「OpenCode Go」设置页（均可配置 API Key + 手动刷新）；rust-linux 为 `dsmon opencode-go` / `dsmon opencode-go set-key [<api_key>]`（无参数时从 stdin 读取，与 `dsmon set-key` 一致）/ `dsmon opencode-go json`
- 显示：三档进度条按用量分级变色（<60% 绿 / 60–79% 琥珀 / ≥80% 红），两平台外观一致

### API 端点与代理

- `api.deepseek.com/user/balance` — 余额查询
- `status.flashcat.cloud/deepseek` — FlashDuty 服务状态（RSC 解析），已弃用 `status.deepseek.com/api/v2`
- 代理：`http_proxy` 配置项 + `proxy_enabled` 开关；禁用时保留代理地址不清除

### 版本工具链

- Rust 固定在 **1.77.2**：1.78+ 把 Windows 普通目标基线提升到 Windows 10，会破坏 Windows 7 支持
- CI 中 Linux 构建在 `rockylinux:8` 容器进行并检查 glibc 符号，保持 RHEL 8 兼容；发布 tag `v*` 触发 Python 构建，`rust-v*` 触发 Rust

## 注意事项

- 修改 API 客户端时需**同步检查 Python 与 Rust 实现**
- Python 版 tkinter + pystray 双事件循环，改动时注意避免死锁
- Rust 双端统一使用 rustls + webpki-roots，根证书内嵌二进制、不依赖系统证书库；根证书数据靠升级 webpki-roots 依赖维护（原 Win7/8.1 根证书脚本已移除，Python 版仅支持 Win10+）
- Rust Windows 版声明系统 DPI 感知（app.manifest）并启用 nwg `high-dpi` feature：控件坐标一律按 96 DPI 逻辑像素书写、运行时自动缩放；字体必须用显式 `size_absolute`，`lfHeight=0` 的映射器默认高度不会随 DPI 缩放
- macOS 构建脚本在 `src/mac` 下运行；改动 macOS 相关文件时遵循现有目录约束
