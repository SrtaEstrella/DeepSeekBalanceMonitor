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
- SignPath Foundation apply: https://signpath.org/apply
- SignPath Foundation terms: https://signpath.org/terms
- SignPath.io documentation: https://docs.signpath.io/

## 推荐方案：SignPath.io（免费版）

本仓库的 Windows release workflow 已集成 SignPath.io 代码签名服务。开源项目应先通过 SignPath Foundation 申请免费 SignPath.io 订阅和证书授权，获批后再配置 GitHub Secrets/Variables，后续发布时 workflow 会自动签名。

适用场景：

- 需要公开发布 Windows `.exe`。
- 开源项目免费使用。
- 不想在 CI 中保存 PFX 证书文件。
- 希望使用 GitHub Actions 自动签名。

限制：

- 免费版仅适用于开源项目。
- 签名请求排队时间可能较长（通常几分钟到几小时）。
- 新版本仍可能出现 SmartScreen 提示，直到文件哈希积累信誉。

## SignPath Foundation 开源项目申请流程

开源项目不再按普通商业账户流程直接申请证书。先访问 https://signpath.org/apply 提交免费 SignPath.io 订阅申请；证书签发给 SignPath Foundation，项目通过 SignPath.io 使用该证书。

### 1. 申请前准备

提交申请前，先把仓库和发布信息整理好：

- 仓库必须公开，项目许可证应为 OSI 认可的开源许可证，且不能包含商业双许可或专有组件。
- 项目必须已经发布过要签名的同类产物，例如 GitHub Release 中已有 Windows `.exe`。
- README、Release 或下载页应清楚说明软件功能，避免审核方无法判断项目用途。
- 产物必须由本仓库源码和构建脚本自动构建；不要用本项目证书签名上游项目二进制。
- 维护者应启用 MFA，并明确谁可以提交代码、审核 PR、批准签名请求。
- 项目不能包含恶意软件、潜在有害程序、黑客工具，或会绕过用户安全控制的功能。

仓库还需要包含 **Code signing policy**。可以在 README、Release 页面或本文档中写明：

```text
Free code signing provided by SignPath.io, certificate by SignPath Foundation.
```

同时列出签名角色：
- Authors/Committers：可直接修改源码的人。
- Reviewers：负责审核外部贡献或重要改动的人。
- Approvers：负责批准 release 签名请求的人。

如果程序会联网或处理用户数据，还应提供隐私政策；如果不会主动传输数据，可以明确说明程序不会在用户未请求时向网络系统传输信息。

### 2. 提交开源项目申请

1. 打开 https://signpath.org/apply。
2. 填写项目名称、仓库 URL、项目主页或下载页、许可证、维护者联系方式。
3. 说明要签名的产物类型，例如 Windows `.exe`、安装包或压缩包。
4. 提交后等待 SignPath Foundation 审核项目声誉、仓库控制权、许可证、发布记录、签名政策和自动构建方式。
5. 如果审核方要求补充信息，优先补齐 README、Release、隐私政策或 Code signing policy，再回复审核。

### 3. 获批后配置 SignPath

获批后，按 SignPath 提供的订阅信息配置项目：

1. 创建或确认 SignPath Project，记录 `Project Slug`。
2. 设置 Repository URL，指向实际发布源码的 GitHub 仓库。
3. 配置 GitHub Actions 作为 Trusted Build System。
4. 在 release 签名策略中启用 Origin Verification；开源签名要求产物来源可验证。
5. 建立 Artifact Configuration，匹配本项目发布的 `.exe` 产物，并确保文件元数据中的产品名和版本号可被检查。
6. 配置 `release` 签名策略和审批人；开源证书签名通常需要每次 release 手动批准。
7. 创建仅用于 CI 的 API Token，角色使用 `Signing Request Creator`。

### 4. 写入 GitHub 配置

取得以下配置值后写入 GitHub Secrets/Variables：

```
SIGNPATH_API_TOKEN: SignPath 中创建的 CI API Token
SIGNPATH_ORG_ID: SignPath 提供或后台显示的 Organization ID
SIGNPATH_PROJECT_SLUG: SignPath 项目的 Project Slug
```

## GitHub fork 仓库配置

以下配置应添加到执行发布 workflow 的仓库，也就是你的 fork 仓库。如果你在上游仓库发布，则配置上游仓库；如果在 fork 发布，则配置 fork。需要对该仓库有写入或管理权限。

### 进入 Actions 配置页

1. 打开 GitHub 仓库主页。
2. 点击 **Settings**。
3. 在左侧 **Security** 区域选择 **Secrets and variables**。
4. 点击 **Actions**。

### 添加 Secret

进入 **Secrets** 标签页，点击 **New repository secret**，添加：

| Name | Value | 说明 |
|------|-------|------|
| `SIGNPATH_API_TOKEN` | SignPath CI API Token | 敏感值，只放在 Secret 中，不要写入 Variables、源码或日志 |

### 添加 Variables

进入 **Variables** 标签页，点击 **New repository variable**，添加：

| Name | Value | 说明 |
|------|-------|------|
| `SIGNPATH_ORG_ID` | Organization ID | SignPath 组织 ID |
| `SIGNPATH_PROJECT_SLUG` | Project Slug | SignPath 项目标识符 |

### 检查 workflow 权限

本项目 workflow 已在 job 中声明：

```yaml
permissions:
  actions: read
  contents: write
  id-token: write
```

含义：
- `actions: read`：SignPath action 使用 `github.token` 读取 GitHub artifact。
- `contents: write`：tag 发布时上传或创建 GitHub Release。
- `id-token: write`：保留给受信构建/签名链路使用。

如果组织或仓库限制了 GitHub Actions 权限，确认 **Settings → Actions → General** 中允许运行 Actions，并且没有阻止 `GITHUB_TOKEN` 读取 artifacts 或写入 release。

### 首次验证

1. 先不配置上述三项，运行 release workflow 应该跳过签名并产出未签名文件。
2. 配齐 `SIGNPATH_API_TOKEN`、`SIGNPATH_ORG_ID`、`SIGNPATH_PROJECT_SLUG` 后，再触发 tag release。
3. 在 Actions 日志中确认出现 `Sign Windows executable` 或 `Sign Windows executables` 步骤。
4. 如果 SignPath 需要审批，进入 SignPath 后台批准 signing request。
5. workflow 完成后下载 Release 产物，用本文后面的 `Get-AuthenticodeSignature` 检查签名。

注意：GitHub 不会把普通 repository secrets 传给来自外部 fork 的 pull request workflow。本项目签名设计用于 tag release 或仓库内受信分支，PR 构建没有签名配置时会自动保持未签名构建。

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
