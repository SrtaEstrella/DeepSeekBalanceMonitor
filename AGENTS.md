# AGENTS.md

跨平台 DeepSeek API 余额监控工具。**权威项目细节见 `CLAUDE.md`（架构、算法、i18n、密钥存储、多平台矩阵）**，本文件只列 agent 容易踩坑的高信号事实。

## 维护范围

本仓库（`legacy` 分支）只维护 Python 版。原 Rust 1.x 的 Windows/Linux 实现（`rust-windows/`、`rust-linux/`）与 Rainmeter / Plasma 6 小组件**已停止维护**，不再同步修改；需要 Rust 版本请使用 **Rust 2.x**：<https://github.com/wenyinos/DeepSeekBalanceMonitor/releases/latest>。

- `src/` 是 Python 运行时，`main.py` 仅入口，勿改动
- 桌面小工具使用 Rust 2.x 的 `dsmon2-widget`，通过 18964 契约读取本版数据；本仓库只维护服务端载荷

## 命令与工具链

- Python 测试（与 CI 一致）：`python -m unittest discover -s tests -v`
  - 单文件：`python -m unittest discover -s tests -p test_core.py`
  - 测试文件无 `__main__` 入口，不能直接 `python tests/test_core.py`

## 关键陷阱

- **API Key 永不写入 `config.json`**：Python 用 Fernet+SQLite（`src/core/secure_settings.py`），OpenCode Go 凭据同样加密入库
- Python 版 UI 文案集中在 `src/core/config.py` 的 `_T` 字典，新增文案必须加进去，不硬编码
- `get_consumption_rate()` 返回 `hourly_rate`（忙时小时速率），非旧版 `daily_rate`
- Python 版 tkinter + pystray 双事件循环，改动时避免死锁
- **桌面小工具（dsmon2-widget，Rust 2.x）从本地接口 18964 读数据**：载荷契约见 `docs/INTERFACES.md` §1，
  实现见 `src/integrations/widget_server.py`（常开、无开关，绑定失败只记日志）。Rainmeter 17654 接口
  已停止维护，只保留代码不再开发。**改动统计口径或载荷字段时，同步 `docs/INTERFACES.md` 并评估小工具展示**

## 发布触发

- tag `v*` → Python 构建（GitHub Actions）
- 发布细节见 `CLAUDE.md` 与 `CODE_SIGNING.md`
