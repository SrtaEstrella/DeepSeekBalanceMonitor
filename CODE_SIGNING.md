# Code Signing & Verification Guide

本文档面向 fork 开发者，说明如何为本项目的可执行文件配置代码签名和验证。

## 先理解 SmartScreen

Windows Defender SmartScreen 主要看两个信号：

- 发布者信誉：文件是否由可信且稳定的发布者证书签名。
- 文件哈希信誉：这个具体文件哈希是否已有足够下载和运行历史。

因此，签名不能保证每次新版本都完全跳过 SmartScreen。每次重新构建后的 `.exe` 哈希都会变化，新文件仍可能被提示"未知发布者/未识别应用"。签名的价值是避免未签名文件的强拦截、显示可信发布者，并让发布者信誉逐步积累。要完全避免 SmartScreen 下载提示，最可靠路径是 Microsoft Store 分发。

参考：

- Microsoft SmartScreen reputation: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation
- Microsoft code signing options: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
- SignPath.io documentation: https://about.signpath.io/

## 推荐方案：SignPath.io（免费版）

本仓库的 Windows release workflow 已集成 SignPath.io 代码签名服务。SignPath 为开源项目提供免费签名服务，fork 开发者只需注册账号并配置 GitHub Secrets/Variables，后续发布时 workflow 会自动签名。

适用场景：

- 需要公开发布 Windows `.exe`。
- 开源项目免费使用。
- 不想在 CI 中保存 PFX 证书文件。
- 希望使用 GitHub Actions 自动签名。

限制：

- 免费版仅适用于开源项目。
- 签名请求排队时间可能较长（通常几分钟到几小时）。
- 新版本仍可能出现 SmartScreen 提示，直到文件哈希积累信誉。

## SignPath.io 注册与配置

### 步骤 1：注册 SignPath.io 账号

1. 访问 https://signpath.io 并注册账号。
2. 使用 GitHub 账号登录（推荐）。

### 步骤 2：创建组织（Organization）

1. 登录后进入 Dashboard。
2. 点击 **Create Organization**。
3. 填写组织名称（建议使用 GitHub 用户名或组织名）。
4. 记录 **Organization ID**（UUID 格式，如 `12345678-1234-1234-1234-123456789abc`）。

### 步骤 3：连接 GitHub 仓库

1. 进入 **Settings** → **Source Code Management**。
2. 点击 **Connect GitHub** 并授权访问。
3. 选择你的 fork 仓库进行连接。

### 步骤 4：创建项目（Project）

1. 点击 **Projects** → **Create Project**。
2. 填写项目信息：
   - **Name**: 项目显示名称（如 `DeepSeekBalanceMonitor`）
   - **Slug**: 项目标识符（如 `deepseek-balance-monitor`）
   - **Repository**: 选择已连接的 GitHub 仓库
3. 记录 **Project Slug**。

### 步骤 5：配置签名策略（Signing Policy）

1. 进入项目设置 → **Signing Policies**。
2. 默认会有一个 `release` 策略，如果没有则创建：
   - **Slug**: `release`
   - **Name**: Release Signing
3. 在策略中配置：
   - **Allowed Artifact Configurations**: 选择 `All` 或手动添加 `.exe` 文件模式
   - **Approvers**: 添加自己作为审批人（免费版可能需要手动审批）

### 步骤 6：创建 API Token

1. 进入 **Settings** → **API Tokens**。
2. 点击 **Create Token**。
3. 填写：
   - **Name**: 如 `github-actions`
   - **Organization**: 选择你的组织
   - **Projects**: 选择你的项目（或选择 `All`）
   - **Roles**: 选择 `Signing Request Creator`
4. 复制生成的 Token（只显示一次）。

### 步骤 7：获取所有配置值

完成以上步骤后，你应该有以下信息：

```
SIGNPATH_API_TOKEN: 你在步骤 6 创建的 Token
SIGNPATH_ORG_ID: 你在步骤 2 记录的 Organization ID
SIGNPATH_PROJECT_SLUG: 你在步骤 4 记录的 Project Slug
```

## GitHub fork 仓库配置

进入你的 fork 仓库：

```
Settings -> Secrets and variables -> Actions
```

### 添加 Secrets

| Name | Value | 说明 |
|------|-------|------|
| `SIGNPATH_API_TOKEN` | 你的 API Token | SignPath API 访问令牌 |

### 添加 Variables

| Name | Value | 说明 |
|------|-------|------|
| `SIGNPATH_ORG_ID` | 你的 Organization ID | 组织 UUID |
| `SIGNPATH_PROJECT_SLUG` | 你的 Project Slug | 项目标识符 |

## 本项目 workflow 行为

### Python Windows workflow

签名文件：
```
dist/DeepSeekBalanceMonitor.exe
```

流程：
1. 使用 PyInstaller 构建 EXE
2. 上传未签名的 EXE 为 GitHub Artifact
3. SignPath 从 Artifact 获取文件并签名
4. 下载签名后的文件
5. 替换原文件并上传到 GitHub Release

### Rust Windows workflow

签名文件：
```
rust-windows/target/*-pc-windows-msvc/release/deepseek-balance-monitor-*-windows-*.exe
```

流程：
1. 构建 x86_64 和 i686 两个架构的 EXE
2. 创建带版本号的 EXE 副本
3. 上传未签名的 EXE 为 GitHub Artifact
4. SignPath 从 Artifact 获取文件并签名
5. 下载签名后的文件
6. 替换原文件并上传到 GitHub Release

### 签名条件

签名步骤只有在以下条件都满足时才执行：
- `SIGNPATH_API_TOKEN` 存在
- `SIGNPATH_ORG_ID` 存在
- `SIGNPATH_PROJECT_SLUG` 存在

没有配置签名时，workflow 会跳过签名步骤并保持原有未签名构建行为。

## 发布流程

### Rust Windows

```bash
git tag -a rust-v1.2 -m "Rust v1.2"
git push origin rust-v1.2
```

### Python Windows

```bash
git tag -a v1.2 -m "v1.2"
git push origin v1.2
```

### 发布后检查

1. 进入 GitHub Actions 查看 workflow 运行状态。
2. 等待构建完成（包括签名步骤，可能需要几分钟）。
3. 检查 Release 页面的文件是否已签名。

## 验证签名

下载 Release 里的 `.exe` 后，在 Windows PowerShell 中运行：

```powershell
Get-AuthenticodeSignature .\DeepSeekBalanceMonitor.exe | Format-List
```

或对 Rust 版本：

```powershell
Get-AuthenticodeSignature .\deepseek-balance-monitor-1.2-windows-x86_64.exe | Format-List
```

成功时应看到：

```
Status : Valid
SignerCertificate : ...
```

如果安装了 Windows SDK，也可以运行：

```powershell
signtool verify /pa /all .\DeepSeekBalanceMonitor.exe
```

## Linux 版本验证

Linux 版本使用 SHA256 校验和验证文件完整性。

### 验证步骤

1. 下载 Release 页面的 tarball 和 checksums.txt 文件：

```bash
# 下载 tarball（替换为实际版本号）
wget https://github.com/OWNER/REPO/releases/download/rust-v1.2/deepseek-balance-monitor-1.2-linux-x86_64.tar.gz

# 下载校验和文件
wget https://github.com/OWNER/REPO/releases/download/rust-v1.2/checksums.txt
```

2. 验证校验和：

```bash
sha256sum -c checksums.txt
```

成功时应看到：

```
deepseek-balance-monitor-1.2-linux-x86_64.tar.gz: OK
```

3. 解压并安装：

```bash
tar -xzf deepseek-balance-monitor-1.2-linux-x86_64.tar.gz
cd deepseek-balance-monitor-1.2-linux-x86_64
./install.sh
```

### 校验和文件格式

Release 中的 `checksums.txt` 文件格式：

```
<sha256hash>  deepseek-balance-monitor-1.2-linux-x86_64.tar.gz
```

### 安全提示

- 始终从官方 GitHub Release 页面下载文件
- 验证校验和后再执行安装脚本
- 如果校验和不匹配，不要使用该文件

## 常见问题

### 签名步骤被跳过

检查 GitHub Secrets/Variables 是否完整。workflow 只有检测到 SignPath 所需配置时才会执行签名。

确认以下三个值都已配置：
- `SIGNPATH_API_TOKEN` (Secret)
- `SIGNPATH_ORG_ID` (Variable)
- `SIGNPATH_PROJECT_SLUG` (Variable)

### SignPath 签名请求失败

常见原因：

1. **API Token 无效或过期**：重新创建 Token。
2. **Organization ID 或 Project Slug 错误**：检查是否复制完整。
3. **签名策略未配置**：确保项目中有 `release` 签名策略。
4. **免费额度用完**：SignPath 免费版每月有签名次数限制。

### 签名成功但 SmartScreen 仍提示

这是可能发生的正常情况。原因通常是新 `.exe` 的文件哈希没有足够信誉。保持稳定发布者身份、稳定下载来源，并等待下载/运行信誉积累。

### 为什么不默认开启签名

签名身份必须属于发布者本人。fork 开发者不能复用上游仓库的签名身份，应使用自己的 SignPath 账号、Azure Trusted Signing、OV/EV 证书或其他合法签名服务。

### SignPath 免费版限制

- 仅适用于开源项目（仓库必须是 public）
- 每月 5,000 次免费签名
- 签名请求可能需要排队等待
- 需要手动审批（如果配置了审批流程）

## 备选方案

### Azure Trusted Signing

如果你有 Azure 订阅，也可以使用 Azure Trusted Signing。需要修改 workflow 文件中的签名步骤和环境变量配置。

参考：https://github.com/Azure/trusted-signing-action

### 传统 OV/EV 证书

如果你已有传统 CA 签发的 OV/EV 代码签名证书，也可以自行修改 workflow 使用 `signtool`。

不建议把 `.pfx` 文件提交到仓库。常见做法是：

1. 将 PFX 转成 base64 后保存为 GitHub Secret。
2. 将 PFX 密码保存为另一个 GitHub Secret。
3. 在 Windows runner 中还原临时 PFX。
4. 使用 `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 /f <pfx> /p <password> <exe>`。
5. 签名后立即删除临时 PFX。

即使使用 EV 证书，当前 SmartScreen 也不再保证新文件首发免提示。

## 不推荐方案

不要用于公开发布：

- 自签名证书。
- 没有时间戳的签名。
- 把 PFX、证书密码、API Token 写入仓库。
- 每次发布更换不同签名身份。

自签名证书只适合内部测试，除非用户机器已通过企业策略信任该证书。

## 安全要求

- 不要提交任何密钥、PFX、token 或密码。
- 不要在日志中打印签名 secret。
- 使用最小权限角色。
- 使用带时间戳的签名。
- 证书或 secret 泄露后立即吊销并轮换。
