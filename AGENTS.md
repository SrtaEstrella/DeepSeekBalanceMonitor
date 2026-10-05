# AGENTS.md

跨平台 DeepSeek API 余额监控工具。**权威项目细节见 `CLAUDE.md`（架构、算法、i18n、密钥存储、多平台矩阵）**，本文件只列 agent 容易踩坑的高信号事实。

## 多实现同步（最高优先级约定）

同一功能有 Python（`src/`、`main.py`）与 Rust 双实现，另有 Rainmeter（Windows）与 Plasma 6（Linux）小组件：

- 改 API 客户端 / 忙时速率算法 / 告警逻辑时，**必须同步检查 Python 与 Rust 两端**
- `src/` 是 Python 运行时，`main.py` 仅入口，勿改动

## 命令与工具链

- Python 测试（与 CI 一致）：`python -m unittest discover -s tests -v`
  - 单文件：`python -m unittest discover -s tests -p test_core.py`
  - 测试文件无 `__main__` 入口，不能直接 `python tests/test_core.py`
- Rust **工具链固定 1.77.2**（`rust-toolchain.toml` 强制），务必用 `cargo +1.77.2 ...`，勿用系统默认工具链：
  - `cd rust-linux && cargo +1.77.2 test --locked` / `cargo +1.77.2 fmt --check`
  - `cd rust-windows && cargo +1.77.2 build --release --target x86_64-pc-windows-msvc --locked`
- Linux 安装产物为 `dsmon`（rust-linux crate 名）；CI 在 rockylinux:8 容器构建并检查 glibc 符号，保持 RHEL 8 兼容

## 关键陷阱

- **API Key 永不写入 `config.json`**：Python 用 Fernet+SQLite（`src/secure_settings.py`），Rust 用 SQLite `secure_settings` 表；Opencode Go 凭据同样加密入库
- Python 版 UI 文案集中在 `src/config.py` 的 `_T` 字典，新增文案必须加进去，不硬编码；CLI 输出固定英文
- `get_consumption_rate()` 返回 `hourly_rate`（忙时小时速率），非旧版 `daily_rate`
- API Key 设为 `demo` 会触发 rust-linux 演示模式（`src/demo.rs`）
- Python 版 tkinter + pystray 双事件循环，改动时避免死锁
- **桌面小工具（dsmon2-widget，Rust 2.x）从本地接口 18964 读数据**：载荷契约见 `docs/INTERFACES.md` §1，
  实现见 `src/integrations/widget_server.py`（常开、无开关，绑定失败只记日志）；Rainmeter 接口 17654 并存，
  旧版小工具退役后再移除。**改动统计口径或载荷字段时，同步 `docs/INTERFACES.md` 并评估两处小工具展示**

## 发布触发

- tag `v*` → Python 构建（GitHub Actions）；`rust-v*` → Rust 构建
- 发布 / 签名 / Rainmeter 打包细节见 `CLAUDE.md` 与 `CODE_SIGNING.md`
