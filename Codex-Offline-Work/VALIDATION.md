# 实际验证记录

范围为当前云端实例的离线构建、静态/格式检查和主机回归测试；没有真实设备启动、外设、Windows 运行或刷写测试。

## 已通过

| 检查 | 实际结果 | 证据 |
|---|---|---|
| Git 与上游固定版本 | HTTPS 只读访问通过；当前目标存在；历史分支/短提交已解析 | `research/UPSTREAM-BOOT.md` |
| 工具链实际能力 | AArch64 GCC ELF 编译、Clang ARM64 EFI PE/COFF 编译链接、UUID 主机编译运行、Mono/NuGet 通过 | `/workspace/.cloud-setup/logs/environment-check.log`、`setup-repeat.log` |
| Python 与 EDK2 安装 | 仓库指定依赖安装，pip check 通过；子模块固定提交 setup 成功；update 两轮各验证 4 项依赖 | `logs/setup-summary.log`、`logs/python-versions.txt`、`logs/submodules.txt` |
| 可复用初始化 | 完整 `setup-cloud.sh` 重复执行退出 0；未改写版本字段、依赖清单或锁文件 | `/workspace/.cloud-setup/logs/setup-repeat.log` |
| 最终 NOSB 完整构建 | 原生命令退出 0，120 项构建后镜像检查通过 | `logs/nosb-build-summary.log`、`Build/SM-T733-Codex/nosb/build.log` |
| 最终 SB 构建 | 修复后再次构建退出 0，120 项构建后镜像检查通过 | `logs/sb-build-summary.log`、`Build/SM-T733-Codex/sb/build.log` |
| FD 与 IMG 独立内容校验 | 两种模式全部通过：FD 长度、ARM64 头、Android v0/page/offset/ID/padding、GZIP CRC/长度、解压后 shim+FD 一致、DTB 一致、FV 头校验与 block map | `logs/nosb-artifacts.json`、`logs/sb-artifacts.json` |
| Python 回归 | **36 tests 通过**：11 项真实封装类测试 + 25 项产物验证器负向/正常测试 | `logs/unit-tests.log` |
| RAM 分区 C 回归 | **15 cases 通过**，实际 C 函数 + UEFI mocks，ASan/UBSan；包括连续 6GiB bank 初块失败后仍尝试后块 | `logs/ram-partition-test.log` |
| BootShim 机器码与复制模型 | 112 字节及指令匹配；明确重现特定正向重叠的数据损坏条件 | `logs/bootshim-audit.json`；只是数据模型，未模拟 CPU/cache/loader |
| DTB / 静态内存 | FDT v17 含合法 NOP 解析通过；4055MiB；FD 未与固定 DTB reservation 相交 | `logs/memory-audit.json` |
| ACPI 只读检查 | DSDT 长度/校验和正确，IASL 反汇编成功 | `logs/acpi-disassemble.log` |
| Windows 驱动来源与架构 | 1210 文件匹配固定 Git blob；170 INF 的 ARM64/CAT 路径检查；5 OEM +77 Silicon SYS 为 ARM64；OEM 300 文件哈希重复生成一致 | `research/driver-*.json`、`research/WINDOWS-DRIVERS.md` |
| Windows 媒体检查工具 | **8 项合成解析检查通过**，包括拒绝 x64 EFI/WIM | `logs/windows-media-selftest.json`；无真实介质 |
| 文件与脚本检查 | 四个 shell helper 的 bash -n、git diff --check 通过；仅两个原有源文件有有意修改 | 最终工作树及源补丁 |

初始及重复 NOSB 构建也通过。修复 RAM 继续尝试逻辑后，重新构建了两种最终候选，并核对两个候选目录内的源补丁与当前实际 Git diff 完全一致。哈希与大小只以 [ARTIFACTS.md](ARTIFACTS.md) 的最终值为准。

## 失败、警告与未执行项

- **DSDT 重新编译失败：19 errors、44 warnings、313 remarks**。反汇编有一个未解析外部方法，另有 `_DEP` 类型、HID 格式和缺失名称等错误。现有构建嵌入原始 AML，因此固件构建成功不表示 ACPI 已通过严格重编译。没有完整 namespace/源代码与硬件证据，未通过删对象、改 ID 或替换其他设备 AML 来掩盖错误。见 `logs/acpi-recompile.log`。
- Azure NuGet 与 Microsoft/Learn 请求收到代理 CONNECT 403。构建采用经过验证的本地 IASL/NASM 路径；微软下载和真实 Windows 介质校验仍未完成。相关域名已保存到环境草稿，保存不代表当前运行时放行。
- 基础版本的 RAM 4GiB 拆分测试和小载荷封装回归**按预期失败**，分别证明旧版本的零余块错误和 `kernel_size=0`。它们是修复证据，不能算作当前通过的用例：`logs/ram-partition-baseline-failure.log`、`logs/postbuild-baseline-regression.log`。
- Python 测试仍显示原有 mkbootimg FileType 流的 ResourceWarning，没有屏蔽警告。RELEASE 构建也保留缺少可选 PDB 复制的 ignored 提示；原始命令退出 0、产物与镜像检查均通过。日志中的 “CRITICAL - Copying Symbols/Override Log” 是上游日志级别，不是本轮命令失败。
- 原始 SoC ACPI 表的部分 checksum 为零、静态和不为零；源码安装路径会重算，故记录为警告而未改动原表。已安装运行时 ACPI 校验和未验收。
- 未执行真实 Windows ISO/WIM 检查、SignTool/Code Integrity 验证、DISM staging、BCDBoot、Windows Boot Manager/内核启动。
- 未执行平板通信、解锁、刷写、磁盘格式化或分区修改；没有硬件通过项，也没有跳过的硬件测试被记作通过。

## 仍限制 Windows 启动的事实

当前设备为 locked rev 9，尚无精确 CHN 固件接受自定义 BOOT 的证据。BootShim 运行时源地址、执行状态及缓存一致性、完整 6GB RAM/GCD 图、动态保留区、UFS/USB 和 ACPI 仍需真实运行证据。驱动还存在测试/社区证书、可选相机缺文件及硬件 ID 集成未知。不能由离线成功推断候选可安全刷入或 Windows 已就绪。

环境的安装与启动草稿已保存，但未发布，也没有新任务恢复验收。当前实例的固件开发环境可用；这些移植限制不会被描述成已完成的硬件支持。

## 正式交付检查

正式交付只核对已完成成果、Git 提交范围、原构建包完整性及下载机制，不开展新的移植研究。原 ZIP 的 CRC 和 SHA-256 核对通过，六份主文档、测试、报告与两组最终候选均存在；拟提交目录只有文本，原大二进制留在 Git 历史之外。新 Actions workflow 的本地语法/结构检查与远程实际执行必须分开记录。
