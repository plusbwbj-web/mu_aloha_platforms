# SM-T733 候选产物与来源

以下为本轮实际构建及离线校验的开发候选，**没有真实设备启动验证，不是可安全刷入或已获 Samsung 认证的镜像**。仅针对 SM-T733 Wi-Fi / SM7325；当前 CHN locked rev 9 的接受条件未知。

## 最终文件

| 文件（相对仓库根目录） | 字节数 | SHA-256 |
|---|---:|---|
| `Build/SM-T733-Codex/nosb/samsung-gts7fewifi_NOSB.img` | 2,748,416 | `bf54c037f65b36f411aa9affe77a908801e742059e10ff2ebf3d7a95acdba138` |
| `Build/SM-T733-Codex/nosb/SM7325_EFI_NOSB.fd` | 2,879,488 | `5caecf881ec7288602368eacb4b15d8df9b67d8e416e8f7c286a19bb95a91f41` |
| `Build/SM-T733-Codex/sb/samsung-gts7fewifi_SB.img` | 2,744,320 | `91bd7a3f72210a48a968bfb468b36a41150a2235c9976d915fb8ebb970da9f01` |
| `Build/SM-T733-Codex/sb/SM7325_EFI_SB.fd` | 2,879,488 | `d6d8c0110d3e9898e2823516652a0704375bc6e721162ed328fad71978d7ff48` |

BootShim：112 bytes，SHA-256 `75f09f1effaf4462033a9cb1f2265c5571360e58c181384df431fbbb8c4ab698`。
目标 Android DTB：652,519 bytes，SHA-256 `5b2978ee329b9292fd336d479c3bafdeadc4c4190965d80932c9ee655c8ef7f1`。
FD 复制区间：`[0x9FC41000,0x9FF00000)`，长度 `0x002BF000`。

## 可下载的本地工程包

`Build/SM-T733-Codex/SM-T733-offline-candidates.zip` 包含两组最终候选、完整构建日志、源码修复文件、补丁、复现脚本、审计及验证记录；ZIP 的 SHA-256 另存同目录 `SHA256SUMS`。不包含 Windows ISO、驱动库二进制、整个 Git 对象库或工具链缓存。

Git 分支为 `codex/sm-t733-offline-prep`，基础 HEAD 为 `81e4762094f338573d39f9d31bcdcff5e924ad7d`；该 HEAD 是原云端候选构建时的基础提交；正式交付将修复与报告集中提交到独立分支，交付提交以 Git 历史及 PR 为准。每个候选目录都有 `source-head.txt`、`source-changes.patch`、`submodules.txt` 及本组 `SHA256SUMS`。最终源码补丁 SHA-256 为 `be14ff3bd4d046e94cd70ab63cb00615bead4d2b914ffb4e6a36414b4a43c41e`。不把旧 HEAD 单独称为已包含修复的提交。

本轮与历史哈希和镜像大小不同：源码框架/工具链不同，且 gzip 默认含时间戳。这不是复现历史文件；独立验证检查的是新 IMG 与本轮 BootShim、FD、目标 DTB 的逐字节一致性。

## 其他交付与缓存

- `Codex-Offline-Work/`：六份主文档、四份专题审计、脚本、回归测试、结构化日志与驱动清单。
- `/workspace/.cloud-setup/toolchain` 与仓库 `.venv`：已准备的工具和 Python 环境。
- `/workspace/.cloud-setup/references/windows_oem_samsung_gts7fewifi`、`windows_silicon_qcom_yupik`：固定来源的原始驱动缓存和 LICENSE，仅供本地调查，没有重打包分发。
- `research/driver-file-hashes.json`：全部 1210 个来源文件的 Git blob 和 SHA-256；CAT 的存在或证书提取不等于 Windows 信任验证。

大二进制不加入 Git 历史。本次新增授权只用于独立分支、PR 和构建包交付，没有设备操作或刷写。使用限制与下一步见 [HANDOFF-TO-DEVICE.md](HANDOFF-TO-DEVICE.md)。

## 正式 GitHub 交付

源代码和报告位于独立分支 `codex/sm-t733-offline-prep`，目标 PR 分支为 `main`，不直接合并。

- 分支入口：https://github.com/plusbwbj-web/mu_aloha_platforms/tree/codex/sm-t733-offline-prep/Codex-Offline-Work
- 原云端构建包：8,933,815 bytes，SHA-256 `3bd356976a375814ca32558ab8cec80f579e1128e59f559ab09d42c5eb744f95`。该包保持原样，不加入 Git 历史。
- `.github/workflows/sm_t733_offline_delivery.yml` 在交付分支 push 时运行已交付的构建与验证脚本，并上传 GitHub Actions Artifact。远程重新生成的 IMG 可因时间戳不同而具有不同哈希，须使用该次 Artifact 内的报告；不能冒充原云端 ZIP。
- Workflow 文件的提交不等于远程执行成功，只有实际成功的 run / artifact 才构成远程下载交付。若 API 或推送权限阻塞，本聊天另附包含原 ZIP、当前提交 Git bundle 和报告的完整交付包。

原构建阶段的文档在原 ZIP 中保持当时状态；正式交付文档以此分支文件为准。
