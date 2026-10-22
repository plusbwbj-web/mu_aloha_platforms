# SM-T733 上游版本与启动路线核实

核实日期：2026-10-21。范围：仅 Git / 源码 / 文档调查，未连接真实设备。目标为 **SM-T733 Wi-Fi、SM7325、6GB/128GB、CHN T733ZCS9DYE1、Android 14、locked bootloader rev 9**。

## 版本身份与来源

通过现有 HTTPS Git 配置执行 `git ls-remote` 和只读 fetch，未推送、未覆盖已有分支。

| 来源 | 实际固定提交 | 核实结果 |
|---|---|---|
| 用户仓库初始状态 | `81e4762094f338573d39f9d31bcdcff5e924ad7d` | 在 Project Aloha 主线提交上新增专用构建 workflow |
| Project-Aloha 主线 `main` | `0b79812897177e9fdd1fb8cb02f05f5338322541` | 与用户初始状态的文件差异仅 `.github/workflows/build_gts7fewifi.yml` |
| qaz6750 `xyz/sm7325/gts7fewifi` | `9e6cb5f1249d18bab50fecb614b4928f6ed55c8b` | 该远程分支仍指向用户提供的历史完整提交，提交说明为将 Guest VM 区域交给 RAM Partition |
| 历史短提交 `6ab400d2` | `6ab400d2b11ca9727645ce8af11d72b56d562d20` | `git cat-file -p` 确认父提交为 `9e6cb5…`，差异仅新增 33 行专用 workflow；它没有额外固件修复 |
| Gezine/edk2-SMT733 | `99107146399f9a61f333a1a104f04c0b842f1642` | 2022 年项目，明确 SM-T733 Wi-Fi 6GB 历史 EFI Shell 先例 |
| Project-Aloha/DualBootKernelPatcher | `36edd373e8d0ff2fd620832f0fc5108f7bcbc84f` | 没有 SM7325 / gts7fewifi 专用配置 |

关键链接：

- [用户基础提交](https://github.com/plusbwbj-web/mu_aloha_platforms/commit/81e4762094f338573d39f9d31bcdcff5e924ad7d)
- [qaz6750 测试分支固定提交](https://github.com/qaz6750/mu_aloha_platforms/commit/9e6cb5f1249d18bab50fecb614b4928f6ed55c8b)
- [6ab400d2 的真实改动](https://github.com/qaz6750/mu_aloha_platforms/commit/6ab400d2b11ca9727645ce8af11d72b56d562d20)
- [Project Aloha 本次核对的主线](https://github.com/Project-Aloha/mu_aloha_platforms/commit/0b79812897177e9fdd1fb8cb02f05f5338322541)

本地仅为审阅增加 `refs/remotes/codex-review/qaz-gts7fewifi` 和 `refs/remotes/codex-review/qaz-6ab400d2`。没有切换、重置或覆盖原始工作分支。工作分支由主代理管理。

**不能从 workflow 的 “Tested” 命名推断任何硬件测试通过。** 本次没有获取到用户 Windows 电脑上的旧构建或原始设备启动日志，用户提供的历史哈希尚未被当作现有产物验证。

## 当前源码与旧测试分支的实质差异

`git diff --shortstat 9e6cb5… 81e47620…` 为 **2693 files changed, 41645 insertions(+), 38701 deletions(-)**，不能将当前主线称为旧测试分支的完全复现。

定向逐字节比较得到：

| 文件 / 子系统 | 比较结果 |
|---|---|
| `BootShim/BootShim.S` | 完全一致，SHA-256 `07b63d309a2ab576006d4da239b6264ca1ab2b5ed7ac735aa5b164e8838f9ee7` |
| SM-T733 `PlatformMemoryMapLib.c` | 完全一致，SHA-256 `8898a5429fb45f1dbe817a14e034263601a61c6d60c492af509a212692a7d161` |
| SM-T733 `ACPI/DSDT.aml` | 完全一致，83,917 bytes，SHA-256 `f4e2efda79fec4f47f1c082f550b5dc9774b368a4138049277a1bfc92527f03e` |
| SM-T733 Android DTB | 完全一致，652,519 bytes，SHA-256 `5b2978ee329b9292fd336d479c3bafdeadc4c4190965d80932c9ee655c8ef7f1` |
| `build_cfg/sm7325.json` | UEFI_BASE / UEFI_SIZE 一致；新版把过去 Python 中的封装参数移到 JSON |
| `PatchedBinaries/UsbConfigDxe.efi` | 同为 86,016 bytes，内容不同；旧 SHA-256 `ab6acb9ed6a4ed681e00b86c3ae6603c1fbd289a5d96176a29143463f1d66337`，当前 `766aad1f370eb46b46a04ec773a838d895270b0eb0e27ae52bd7e3c6bffb3cbd` |
| 设备 PCD | 当前 RetailModel 为 `gts7fewifi-T733XXS9DYF1`；旧版为 `gts7fewifi`。旧版显式 `PcdStorageHasUFS3|0` 已删除 |
| RNG / 驱动列表 | 当前通过 INF 更早引入 RNG；部分 PatchedBinaries INF 有格式 / 生成日期变化 |
| 公用框架 | RAM 分区驱动、构建工具、Crypto、子模块和 Python 依赖均有更新 |

以上差异并不单独证明新版有缺陷或旧版更适用。尤其不能仅凭 `T733XXS9DYF1` 字符串推断与 **CHN T733ZCS9DYE1** 的二进制接口兼容，也不能凭该字符串认定不兼容。需要实际原厂固件、协议和设备日志比对；本次不擅自替换 USB 二进制或回滚公用内存代码。

主要 EDK2 子模块不同：

| 子模块 | 旧测试分支 | 当前基础提交 |
|---|---|---|
| MU_BASECORE | `81a4bd998e8fa500abe149f380437aeb7ccc0cd2` | `c6d8901de2ffaabc6110c81e90a915f84795fbd5` |
| Common/MU | `039747f3b2c13df10b4fe4844e864c3095f98212` | `49625b8f6cabe7e4d9797d192c354b14af0490d1` |
| Common/MU_OEM_SAMPLE | `e798945fbe64baad73e9c4ec7cfb26efaa95d4e3` | `15c43745132537ef047d0fac6403ed78e520f3f8` |
| Features/CONFIG | `d08c5af327768d2820bbd030ca5af443be33bce8` | `6789841f35d417fafbe6a9ff9427360b52ca37d9` |
| Features/DFCI | `401e480fe46d348115a6fe94a878d50069b8098c` | `cd33bec609f4d55dc753eb7b485ea251a5fb6be6` |
| SurfaceDuoACPI | `cb94d339a66b2b7b1802ffdc6ec52c8accb71326` | `d742758fe575c08b5278d84fec1b3b313551a587` |

详细比较的机器输出另存于 `/workspace/.cloud-setup/references/upstream-comparison.json`；它是当前工作区证据，不是必须提交的第三方源码。

## 有直接机型证据的路线

**优先研究 SM-T733 专用 Android BOOT 镜像承载 UEFI 的路线。** 这里的“优先”只表示它具有更多机型证据和较少新增代码；不表示 locked rev 9 现在可以接受候选镜像。

[Gezine README](https://github.com/Gezine/edk2-SMT733/blob/99107146399f9a61f333a1a104f04c0b842f1642/README.md#L1-L33) 明确：SM7325 Wi-Fi、6GB RAM，作者报告屏幕正常及能进入 EFI Shell；同时列出 **UFS、SDcard、USB、ACPI 不工作**。README 明确排除 LTE / 5G 机型。

[历史封装脚本](https://github.com/Gezine/edk2-SMT733/blob/99107146399f9a61f333a1a104f04c0b842f1642/build_debug.sh#L7-L11) 是 `gzip(FD) + SMT733.dtb`，再与空 ramdisk 组成 Android boot image。[README 记录的历史 BOOT 分区路线](https://github.com/Gezine/edk2-SMT733/blob/99107146399f9a61f333a1a104f04c0b842f1642/README.md#L55-L58) 只作为历史证据，未在本任务执行。

旧项目 [FDF](https://github.com/Gezine/edk2-SMT733/blob/99107146399f9a61f333a1a104f04c0b842f1642/SMT733/SMT733.fdf#L27-L34) 基址为 `0x9FC00000`、大小 `0x200000`；当前 Aloha 为 `0x9FC41000`、`0x2BF000`，并在 FD 前添加 BootShim。旧版的 6GB 静态配置不能当作新版动态 RAM 分区路径已完成验证，也不能混用旧 FD 与新 BootShim。

用户提到的另一份 4GB / 64GB、Windows 11 22621.1 桌面案例没有提供可追溯公开 URL、固定版本或设备日志。此次未独立复现或证实该案例，不以其作为当前 6GB/128GB 机型的验收依据。

## 双启动补丁器的适用性

[固定版本 Config 目录](https://github.com/Project-Aloha/DualBootKernelPatcher/tree/36edd373e8d0ff2fd620832f0fc5108f7bcbc84f/Config) 只有 **SM7125、SM8150、SM8250、SM8250DT、SM8550**。对克隆内容搜索 `SM7325|gts7fewifi|T733` 未发现匹配。

[Hotdog shellcode](https://github.com/Project-Aloha/DualBootKernelPatcher/blob/36edd373e8d0ff2fd620832f0fc5108f7bcbc84f/ShellCode/ShellCode.Hotdog.S#L3-L10) 注释明确针对 OnePlus 7T Pro GPIO125。这说明按键选择逻辑依赖具体设备，不能把现有配置直接改名为 SM7325。

本次不为追求双启动而引入未经验证的 SM-T733 GPIO / 内核补丁。它仍是未来独立移植工作，不作为当前候选镜像准备的前置条件。

## Aloha IMG 符合什么，尚未证明什么

旧测试分支的 [PostBuild.py](https://github.com/qaz6750/mu_aloha_platforms/blob/9e6cb5f1249d18bab50fecb614b4928f6ed55c8b/Platforms/KodiakPkg/PythonLibs/PostBuild.py) 与当前 [`PythonLibs/PostBuild.py`](https://github.com/plusbwbj-web/mu_aloha_platforms/blob/81e4762094f338573d39f9d31bcdcff5e924ad7d/PythonLibs/PostBuild.py) 都构造：

`Android boot v0 { kernel = gzip(BootShim + SM7325_EFI.fd) + android-gts7fewifi.dtb; empty ramdisk }`

当前封装参数来自 `build_cfg/sm7325.json`：page size 4096、base 0、空 cmdline、OS version 11.0.0、patch level 2023-04-01。历史和当前代码均选择设备专属 `android-gts7fewifi.dtb`。镜像头的 OS version / patch level 是元数据，不能据此证明或否定 Android 14 bootloader 的兼容性。

因此，**源码层面符合项目已使用的 Android BOOT 容器路线**。实际候选镜像是否满足该结构，由本次产物验证器和构建记录单独给出。结构通过后仍有以下未知：

- 当前三星 ABL 是否允许该 header 版本、kernel load address、GZIP 解压布局和尾随 DTB；需比较该设备确切原厂 BOOT / VENDOR_BOOT / DTBO / VBMETA 以及启动日志。
- Samsung 特有尾部、签名、AVB chain、回滚索引和允许的二进制版本。项目的普通 mkbootimg 过程不等于三星原厂签名，也不自动获得接受权限。
- 实际 BOOT 分区容量、正确分区标识与 PIT，不能把历史 `/dev/block/sda19` 当作当前已确认映射。
- 解压位置是否与 BootShim 目的区域重叠、启动时 EL / MMU / cache 状态，以及动态保留内存。
- 原厂 TZ / ABL 等版本接口是否与随仓库的专有 EFI 驱动兼容。

不通过猜测添加 Samsung 标记、伪造签名、关闭安全验证或套用其他设备镜像来“修复”这些未知项。

## locked bootloader 与合法 OEM 条件

一般 AVB 约定：**LOCKED 状态下验证错误是致命错误**；UNLOCKED 的允许错误路径需要 bootloader 明确提供。此处依据是 AOSP AVB README 的 [LineageOS 镜像固定版本](https://github.com/LineageOS/android_external_avb/blob/91f1bfc948d35265c3b1e5e97bf1c410e65d18fa/README.md#locked-and-unlocked-mode)，内容已实际下载并检查；它不是对 Samsung rev 9 私有实现的逆向证明。

该文档还规定解锁转换需物理用户确认，并会清除用户数据。其通用 fastboot 示例 **不应被转写为三星设备操作命令**。当前云任务没有设备连接，也没有确认目标设备是否提供可用的 OEM 解锁机制、是否受地区 / 账户 / KG / RMM / 企业管理限制。

Samsung bootloader 解锁和 Knox 状态可能带来数据擦除及不可逆安全功能影响，应在设备专用支持信息和用户备份完成后，由用户另行决定。本次没有宣称其 OEM 开关必定可用，也没有解锁、root 或尝试绕过安全启动。

**UEFI Secure Boot 的 SB / NOSB 与 Samsung Android Bootloader 锁定是两个层次。** SB 构建控制进入自建 UEFI 后的 EFI 镜像验证策略，不能把候选 BOOT 镜像变成三星原厂签名，也不能解锁 Android 启动链。

原始 `source.android.com` 文档请求被当前网络代理返回 403；已改用可访问的源码镜像作一般 AVB 行为参考。未获取到可验证的 **CHN T733ZCS9DYE1 rev 9** OEM 解锁及自定义 BOOT 启动兼容材料。

## 可离线验收与硬件门槛

| 可在本轮离线检查 | 必须留下的真实设备条件 |
|---|---|
| 固定源提交、构建命令、依赖和日志 | 型号 / 地区 / 固件 / 容量 / 二进制版本的现场核对 |
| BootShim 指令与头、FD 大小、布局及固定内存重叠分析 | 实际 RAM 分区表、ABL 交付内存、EL / cache / MMU 状态 |
| IMG header、offset、GZIP CRC、FD 与 DTB 字节一致性 | ABL 接受和解压候选镜像、UEFI 真正启动 |
| ACPI 校验、驱动列表和静态设备 ID 调查 | UFS / USB / 显示 / 输入 / ACPI / Windows 驱动实际工作 |
| Windows 部署材料的合法来源和离线验证脚本 | Windows Boot Manager / 内核进入桌面及全部 6GB 内存可见 |

第一步设备工作应是用户自行完成备份和只读身份 / 状态核对，确认 OEM 解锁资格及风险，随后再决定是否授权任何设备修改。不能直接从“离线格式验证通过”跳到刷写候选 IMG。
