# Repository Guidelines

## Project Structure & Module Organization

本仓库是一个 Python Windows 托盘应用，用于监控 DeepSeek API 余额。运行时代码放在
`src/`，`main.py` 只作为入口。`src/api_client.py` 负责余额接口请求，
`src/config.py` 管理配置、日志和中英文文案，`src/icon_renderer.py` 生成托盘图标，
`src/settings_dialog.py` 负责设置窗口，`src/app_state.py` 保存共享状态，
`src/tray_app.py` 组装应用流程。构建和辅助脚本放在 `scripts/`，根目录保留
`README.md`、`requirements.txt`、`preview_taskbar.png` 等项目级文件。

## Build, Test, and Development Commands

```bash
pip install -r requirements.txt
python main.py
python scripts/test_api.py YOUR_DEEPSEEK_API_KEY
scripts\build_exe.bat
```

- `pip install -r requirements.txt`：安装运行依赖。
- `python main.py`：从源码启动托盘应用。
- `python scripts/test_api.py ...`：使用真实 API Key 验证 DeepSeek 接口连接。
- `scripts\build_exe.bat`：生成图标并构建 Windows 单文件可执行程序。

## Coding Style & Naming Conventions

使用 Python 3.10+，缩进为 4 个空格。函数、变量和模块使用 `snake_case`，常量使用
`UPPER_CASE`。保持现有的直接函数式写法，公共辅助函数优先补充类型标注。新增界面文案
应写入 `src/config.py` 的 `_T` 翻译表，不要散落在各 UI 模块。修改时保持小范围，
不要顺手重构无关代码。

## Testing Guidelines

当前没有正式测试目录。涉及 API 的改动，运行
`python scripts/test_api.py YOUR_DEEPSEEK_API_KEY` 验证连接和响应解析。涉及 UI、配置、
图标或托盘行为的改动，应在 Windows 上运行 `python main.py`，手动检查首次启动、设置
保存/读取、托盘菜单、余额不足状态和退出流程。不要提交真实 API Key 或本地配置文件。

## Commit & Pull Request Guidelines

提交历史以简短说明为主，中文描述和 `fix:` 前缀都可接受。每次 commit 只做一件事，
示例：`fix: handle empty balance response`、`优化设置窗口文案`。Pull Request 应说明
用户可见变化、列出手动验证步骤、标明配置或 API 影响；如果改动托盘图标或设置窗口，
附上截图。

## Security & Configuration Tips

配置文件位于 `%APPDATA%\DeepSeek Balance Monitor\config.json`，日志也写入同一目录。
禁止在源码、脚本、截图或文档中硬编码 API Key、token 或其他密钥。`build/`、`dist/`、
`*.spec`、`app_icon.ico`、日志等生成物应保持在版本控制之外。
