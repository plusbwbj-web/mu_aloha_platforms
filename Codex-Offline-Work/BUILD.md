# SM-T733 云端构建与复现

工作目录：`/workspace/mu_aloha_platforms`。基础提交 `81e4762094f338573d39f9d31bcdcff5e924ad7d`，本轮分支 `codex/sm-t733-offline-prep`。正式交付把源码修复、测试和文档提交到此独立分支，提交标识以 Git 历史及 PR 为准。云端候选目录的 `source-changes.patch` 精确记录原构建参与的两项源码修改，`source-head.txt` 是当时的基础提交，不是正式交付提交。

## 已验证环境

Debian 13 x86_64、Python 3.12.14、Git 2.52.0；Clang/LLVM/LLD 19.1.7、AArch64 GCC 14.2、NASM 2.16.03、IASL 20250404、Mono 6.12.0.199。机器有约 32GiB 内存；使用 cgroup 允许的 4 个 CPU 并行，不构建所有平台。

工具安装于 `/workspace/.cloud-setup/toolchain`，Python 依赖位于仓库忽略的 `.venv`，APT 的索引及包缓存也在 `/workspace/.cloud-setup`。APT 保留 Debian 签名、包哈希和 TLS 验证；NuGet 使用 edk2-pytool 固定的 6.4.0 SHA-256 校验。没有需要新增的构建密钥。

当前 Azure NuGet 源请求返回代理 CONNECT 403。使用 Stuart 正式支持的 `override_id`，在忽略目录 `.venv/local-tools` 配置本地路径 descriptor，只选择已经过 Debian 包校验的 NASM/IASL。其他 4 项实际外部依赖、所有构建插件和镜像验证保留启用。NASM/IASL 版本不同于 Azure 固定包，不声称二者二进制等同；实际目标构建用于检验本轮兼容性。

## 初始化和构建

每个 Codex Cloud 任务本身已经隔离，使用现有 checkout；没有必要创建 worktree。保留已有源文件及用户改动。

```bash
cd /workspace/mu_aloha_platforms
bash Codex-Offline-Work/tools/setup-cloud.sh
source Codex-Offline-Work/tools/activate.sh
bash Codex-Offline-Work/tools/build-sm-t733.sh nosb
```

这三步已实际执行。初始化脚本包含工具链、Python 依赖检查、固定提交子模块 setup、Stuart update、BootShim 强制重建及真实编译/链接 smoke checks。子模块首次准备需要下载数 GB Git 对象，后续复用有效缓存。

构建脚本直接调用 `stuart_build`，检查原始退出状态，以 `TARGET_DEVICE=samsung-gts7fewifi`、`TARGET=RELEASE`、`MAX_CONCURRENT_THREAD_NUMBER=4` 构建。它使用 `make -B` 避免切换目标后复用旧 BootShim，再运行独立的完整候选产物检查。不要并行构建 SB/NOSB：二者共享 `Build/KodiakPkg/RELEASE_CLANGPDB`。

可选的 UEFI Secure Boot 模式：

```bash
bash Codex-Offline-Work/tools/build-sm-t733.sh sb
```

SB 控制自建 UEFI 中的 EFI 镜像策略。它不解锁 Samsung bootloader，也不赋予 Android IMG 三星原厂签名。NOSB 是本轮主要开发候选；SB 不构成部署或受信任密钥已经验证的证明。

## 产物与日志

- `Build/SM-T733-Codex/nosb/`：NOSB FD、IMG、BootShim、构建日志、源差异、固定子模块清单和 SHA256SUMS。
- `Build/SM-T733-Codex/sb/`：同类 SB 产物。
- `Codex-Offline-Work/logs/{nosb,sb}-artifacts.json`：独立结构与哈希检查。
- `/workspace/.cloud-setup/logs/`：初始安装、初始化、构建及重复验证的完整日志。

大二进制和工具缓存留在既有忽略的 `Build/` 或 checkout 外，不加入 Git 历史。IMG 的 gzip 默认时间戳会使重复封装的哈希不同；FD 也不保证跨日期或工具版本逐位可重复。这里的“复现”指固定源码与依赖流程能再次成功构建并通过内容检查。

## 已知脚本问题及环境配置

原 `build_setup.sh` 调用 `timebuild.sh` 改写受 Git 跟踪的版本字段，并包含无效的 LLVM 路径；原 `build_uefi.py` 不能可靠传播子命令失败。新辅助脚本绕开这些入口，没有扩大重构。

已保存环境草稿的 `install_script`、`start_skill`，以及自定义域名 `dist.nuget.org`、`pkgs.dev.azure.com`、`www.microsoft.com`、`learn.microsoft.com`，保留既有包管理器网络预设。后两项用于后续核对微软官方介质入口与部署文档。网络草稿保存本身不改变当前运行时；本轮构建已通过本地工具路径完成，微软页面仍未能读取。请在环境设置中审阅、保存并发布该环境，发布将保留已准备的文件快照。此任务没有执行发布，也尚未独立验证新任务恢复。

这是命令行固件工作流，无需后台服务；新任务中仍需重新 source 激活脚本。不能依赖上次 shell 的环境变量继续生效。

## GitHub Actions 下载交付

新增 `sm_t733_offline_delivery.yml`，只在 `codex/sm-t733-offline-prep` 分支 push 或显式手动触发时执行。它在 Debian 13 容器内使用交付脚本，顺序构建 NOSB/SB 并上传候选、校验结果、源码和文档，保留 30 天。源码提交不包含 ZIP/FD/IMG。远程构建是否实际运行及成功，应以 GitHub run 状态为准，不能用本轮云端已通过的结果代替。
