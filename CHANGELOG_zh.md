# 更新日志

所有值得记录的变更均记录于此。

## Python v1.2.1-dev (待发布)

### 变更

- API Key 加密存储统一为 Fernet + SQLite，保留原方案兼容性回退；save_config() 自动清空明文字段
- 代理开关调整为 proxy_enabled 复选框 + 地址输入框，关闭时保留地址不清除
- 设置页微调，规整标题，移除 footer 中的上次查询和余额行

## Rust v1.2 (2026-05-11)

### 新增

- Rust Windows 与 Rust Linux 版本号统一为 `1.2.0`
- SQLite `secure_settings` 加密存储 API Key（Rust Windows / Linux）
- 旧 `config.json.api_key` 明文自动迁移至加密存储
- Rust demo 模式：API Key 填入 `demo` 触发，数据写入独立 `demo_mode_balance` 表
- Rust Linux `dsmon set-key` 命令，加密更新 API Key
- Rust Linux `dsmon set <field> <value>` 命令，单字段配置更新
- Rust Linux 安装器首次检测到无 Key 或 Key 无效时提示输入
- Rust Linux `uninstall.sh` 卸载脚本（保留 Plasma 小组件）
- Plasma 6 小组件液态玻璃风格视图，支持余额、上次查询、服务状态、可用天数、刷新控制、emoji 状态文字
- Rainmeter 桌面小组件，通过本地 `127.0.0.1:17654` 接口获取数据；Rust Windows 现已提供该接口
- GitHub Actions 通过 `rmskin-builder` 自动打包 `.rmskin`

### 变更

- Rust Linux daemon 每次轮询重新读取配置，CLI 修改即时生效
- Rust Linux CLI 固定英文输出，不弹桌面通知
- Rust Windows 首次无 Key 时弹出设置对话框
- Rust Windows/Linux 分离 `ui_language`（GUI）与 `language`（CLI 固定英文）
- Rust CSV 导出默认保存到用户主目录，文件名带日期后缀
- Rust demo 余额不污染真实 `balance_history` 表
- Plasma 小组件设置改用 `dsmon set` 命令

## Python v1.2 (2026-05-11)

### 新增

- 自定义图标配色：5 套预置主题（默认/高对比/明亮/暗色模式/纯灰度）+ 自定义 hex 颜色 + 图标描边开关
- 历史记录页：分页表格 + 折线图 + 消耗速率分析，支持 CSV 导出
- 消耗速率估算：基于 topped 余额的非递增区间加权平均，在余额通知和历史页同步显示
- Demo 模式：`--demo` 启动，右键开发者面板调节各种参数
- HTTP 代理支持
- API Key 加密存储于 Windows 凭据管理器，config.json 降级为迁移入口
- MacOS WebView 设置界面
- 核心 API 解析和状态迁移的单元测试覆盖

### 变更

- 余额通知卡片：emoji 前缀 + 仅显示相对时间 + 服务状态调整到时间之前
- API 服务状态同步写入本地数据库
- 设置、历史、开发者面板共享 Tk 根窗口，避免窗口冲突；历史和开发者面板支持重复唤起聚焦
- 设置页底部显示版本号/贡献者/项目链接
- MacOS 构建脚本增加 DMG 打包

## Rust v1.1 (2026-05-10)

### 新增

- Rust Windows 原生托盘程序，支持 Win7+
- Rust Linux CLI + KDE Plasma 6 小组件
- Rust 历史功能：图表、天数/币种筛选、CSV 导出、`dsmon history` CLI
- Plasma 小组件守护进程启停 + 命令错误通知
- Windows 7/8.1 根证书更新辅助脚本

### 修复

- 修复 Plasma 小组件配置页
- Rust Windows 构建补充应用图标

## Python v1.1 (2026-05-10)

### 新增

- API 服务状态轮询（`status.deepseek.com`），托盘图标 API 异常时显示暖灰色，状态变化独立通知
- 托盘菜单「充值」直达 `platform.deepseek.com/top_up`
- SQLite 余额历史存储，日志与记录自动清理，可配置保留天数（默认 30 天）
- 社区移植 Python MacOS 应用程序，Keychain 加密
- 新增 CONTRIBUTING.md 供社区移植者参考
- GitHub Actions 自动构建，打包 Python EXE 并挂到 Release

### 变更

- 低余额提醒三选一：不提醒 / 持续提醒 / 仅提醒一次，默认仅一次
- 余额通知卡片重构：固定标题 + 内嵌明细 + 服务状态常驻
- 设置保存时校验字段数值范围或非法输入，并弹出警告
- 移除 `requests`，改用 stdlib `urllib.request`

## Rust v1.0.1 (2026-05-09)

内部开发版本号为 Windows v0.1.0/v0.1.1 及 Linux v0.2.0

### 新增

- 初始 Rust Windows 原生构建
- GitHub Actions Rust Windows 构建产物发布流程
- 编写 Rust Windows 构建文档
- 将 Rust Windows 移植合并入上游 Python 主分支
- 初始 Rust Linux `dsmon` 发布构建
- Linux 打包基础，支持命令行余额查询

### 修复

- Rust Windows 启动构建流程加固
- Rust workflow tag 触发器调整为 `rust-v*`，避免与 Python 版冲突
- 更新 Rust 移植同步文档

## Python v1.0.1 (2026-05-09)

### 变更

- 仓库结构重组为 `src/` 和 `scripts/`
- 废弃货币选择逻辑，因每个账号对应固定单一币种
- 设置对话框行为改进
- API Key 字符编码加固
- 图标配色和提醒开关优化
- README 文档更新：推荐直接下载为首选安装方式，优化预览图
- 代码审计、格式清理

## Python v1.0.0 (2026-05-06)

### 新增

- 首次公开发布 Python Windows 托盘应用
- 定时 DeepSeek 余额查询
- 低余额提醒
- 设置对话框（API Key、查询间隔、阈值、语言、开机自启）
- 托盘图标渲染
- Windows 可执行文件打包脚本
