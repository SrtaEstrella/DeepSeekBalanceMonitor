# Windows Code Signing Guide

本文档面向 fork 开发者，说明如何为本项目的 Windows 可执行文件配置代码签名。

## 先理解 SmartScreen

Windows Defender SmartScreen 主要看两个信号：

- 发布者信誉：文件是否由可信且稳定的发布者证书签名。
- 文件哈希信誉：这个具体文件哈希是否已有足够下载和运行历史。

因此，签名不能保证每次新版本都完全跳过 SmartScreen。每次重新构建后的 `.exe` 哈希都会变化，新文件仍可能被提示“未知发布者/未识别应用”。签名的价值是避免未签名文件的强拦截、显示可信发布者，并让发布者信誉逐步积累。要完全避免 SmartScreen 下载提示，最可靠路径是 Microsoft Store 分发。

参考：

- Microsoft SmartScreen reputation: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation
- Microsoft code signing options: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
- Azure Trusted Signing Action: https://github.com/Azure/trusted-signing-action

## 推荐方案：Azure Trusted Signing

本仓库的 Windows release workflow 已预留 Azure Trusted Signing。fork 开发者只需要在自己的 fork 仓库配置 Azure 账号信息和 GitHub Secrets/Variables，后续发布时 workflow 会自动签名。

适用场景：

- 需要公开发布 Windows `.exe`。
- 不想在 CI 中保存 PFX 证书文件。
- 希望使用 GitHub Actions 自动签名。

限制：

- Azure Trusted Signing 需要可用区域和身份验证资格，个人/组织支持范围以 Microsoft 当前文档为准。
- 首次配置需要 Azure 订阅、身份验证、Trusted Signing Account 和 Certificate Profile。
- 新版本仍可能出现 SmartScreen 提示，直到文件哈希积累信誉。

## Azure 侧准备

1. 在 Azure Portal 创建或选择一个订阅。
2. 创建 Trusted Signing Account。
3. 完成身份验证。
4. 创建 Certificate Profile。
5. 创建 Microsoft Entra App Registration，或为 GitHub Actions 配置 OpenID Connect。
6. 将该应用或联合身份授予签名权限。

需要的角色通常是：

```text
Trusted Signing Certificate Profile Signer
```

建议把权限授予到 Certificate Profile 或 Trusted Signing Account 的最小可用范围，不要授予订阅级过大权限。

## GitHub fork 仓库配置

进入你的 fork 仓库：

```text
Settings -> Secrets and variables -> Actions
```

添加 Secrets：

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_CLIENT_SECRET
```

`AZURE_CLIENT_SECRET` 是可选项。如果你使用 GitHub OIDC 联合身份，可以不设置 client secret，但必须正确配置 Azure Federated Credential，并确保 workflow 有 `id-token: write` 权限。

添加 Variables：

```text
AZURE_TRUSTED_SIGNING_ENDPOINT
AZURE_TRUSTED_SIGNING_ACCOUNT_NAME
AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE_NAME
```

示例 endpoint：

```text
https://eus.codesigning.azure.net/
```

实际 endpoint 必须和你的 Trusted Signing Account 所在区域一致。

## GitHub OIDC 建议配置

如果使用 OIDC，建议至少为正式发布 tag 配置 Federated Credential。

Rust Windows release tag：

```text
repo:<owner>/<repo>:ref:refs/tags/rust-v*
```

Python Windows release tag：

```text
repo:<owner>/<repo>:ref:refs/tags/v*
```

如果你希望在分支上测试签名，也可以额外添加：

```text
repo:<owner>/<repo>:ref:refs/heads/Rust-Dev
repo:<owner>/<repo>:ref:refs/heads/main
```

分支签名会消耗签名额度，不建议长期对所有 push 都启用。

## 本项目 workflow 行为

Rust Windows workflow 会签名这些文件：

```text
rust-windows/target/**/release/deepseek-balance-monitor-*-windows-*.exe
```

Python Windows workflow 会签名：

```text
dist/DeepSeekBalanceMonitor.exe
```

签名步骤只有在必要变量存在时才执行。没有配置签名时，workflow 会跳过签名步骤并保持原有未签名构建行为。

## 发布流程

Rust Windows：

```bash
git tag -a rust-v1.2 -m "Rust v1.2"
git push origin rust-v1.2
```

Python Windows：

```bash
git tag -a v1.2 -m "v1.2"
git push origin v1.2
```

不要在没有验证 workflow 的情况下覆盖已有 tag。需要重新发布同一版本时，优先重新上传 Release 资产；只有明确知道后果时才移动 tag。

## 验证签名

下载 Release 里的 `.exe` 后，在 Windows PowerShell 中运行：

```powershell
Get-AuthenticodeSignature .\deepseek-balance-monitor-1.2-windows-x86_64.exe | Format-List
```

成功时应看到：

```text
Status : Valid
SignerCertificate : ...
```

如果安装了 Windows SDK，也可以运行：

```powershell
signtool verify /pa /all .\deepseek-balance-monitor-1.2-windows-x86_64.exe
```

## 传统 OV/EV 证书方案

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
- 把 PFX、证书密码、Azure client secret 写入仓库。
- 每次发布更换不同签名身份。

自签名证书只适合内部测试，除非用户机器已通过企业策略信任该证书。

## 常见问题

### 签名步骤被跳过

检查 GitHub Secrets/Variables 是否完整。workflow 只有检测到 Azure signing 所需配置时才会执行签名。

### Azure Trusted Signing 返回 403

通常是权限或身份配置问题。检查：

- `AZURE_TENANT_ID` 是否属于正确租户。
- `AZURE_CLIENT_ID` 是否对应正确 App Registration。
- Federated Credential 的 repo、branch、tag pattern 是否匹配当前 workflow。
- 是否授予 `Trusted Signing Certificate Profile Signer`。
- Certificate Profile 名称和账号名称是否正确。

### 签名成功但 SmartScreen 仍提示

这是可能发生的正常情况。原因通常是新 `.exe` 的文件哈希没有足够信誉。保持稳定发布者身份、稳定下载来源，并等待下载/运行信誉积累。

### 为什么不默认开启签名

签名身份必须属于发布者本人。fork 开发者不能复用上游仓库的签名身份，应使用自己的 Azure Trusted Signing、OV/EV 证书或其他合法签名服务。

## 安全要求

- 不要提交任何密钥、PFX、token 或密码。
- 不要在日志中打印签名 secret。
- 使用最小权限角色。
- 使用带时间戳的签名。
- 证书或 secret 泄露后立即吊销并轮换。
