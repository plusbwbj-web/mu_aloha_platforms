# BootShim 与 Android 封装审计

本节基于基础提交 `81e4762094f338573d39f9d31bcdcff5e924ad7d` 和本工作分支的封装检查修复。对象只包括 SM-T733 / `samsung-gts7fewifi`；没有连接真实平板。下述二进制检查、数据复制模型和单元测试均不是设备启动验证。

## 已确认的二进制与地址

实际使用 Clang 19 编译并用 LLVM 反汇编了 [BootShim.S](../../BootShim/BootShim.S)。生成的 `BootShim.bin` 为 112 字节，首条指令为 `adr x1, _Payload`，`_Payload` 位于 `+0x70`，恰好指向随后拼接的 FD。

| 字段或边界 | 实际结果 |
|---|---|
| ARM64 magic，偏移 56 | `41 52 4d 64` / `ARM\x64` |
| 偏移 8 的 64 位数 | `0x9FC41000`，当前代码把它作为复制目的地址 |
| 偏移 16 的 64 位数 | `0x002BF000` / 2,879,488 字节，复制计数 |
| FD 目标区间 | `[0x9FC41000, 0x9FF00000)` |
| 目的地址对齐 | 4KiB 对齐 |
| 复制循环 | 每次 `ldp` + `stp` 16 字节，共 179,968 次 |
| 源指针 | 运行时 shim 入口地址 `+112`，不是由 Android IMG 文件头单独决定 |

[build_cfg/sm7325.json](../../build_cfg/sm7325.json) 与 [Kodiak.fdf](../../Platforms/KodiakPkg/Kodiak.fdf) 的基址及长度一致。FD 长度和所含载荷必须由最终产物校验再次确认。

## 复制正确性条件及未闭合风险

[BootShim.S:36](../../BootShim/BootShim.S#L36) 只有正向复制，没有 memmove 的反向路径。令 FD 源区间为 `[S,S+N)`，目的区间为 `[D,D+N)`：

- `S == D` 时直接跳过复制。
- 源与目的不相交时，16 字节循环在 `N > 0` 且 `N % 16 == 0` 的条件下准确复制 N 字节，不多读一块。
- `S < D < S+N` 时，写入会覆盖尚未读取的源数据。对实际指令编码核验后运行的 [数据复制模型](../tools/bootshim_audit.py) 重现了此类损坏。
- `D < S` 的重叠在纯数据复制模型中可正确复制，但不能据此认定启动安全：目的区域还可能覆盖正在执行的 shim 代码 `[S-112,S)`。模型明确不模拟取指、缓存、异常或设备内存属性。
- 若复制长度为零或非 16 的倍数，原汇编的 `subs` / `b.ne` 无法正常在所期望的边界退出。当前目标配置有效，新增封装检查会拒绝这些配置。

当前云端没有目标平板 bootloader 的运行时解压地址、实际 DRAM 布局、UEFI 内存映射或启动日志。因此不能离线证明 S 与 D 不重叠，也不能将 `[D,D+N)` 判定为对当前国行 rev 9 设备安全。没有尝试猜测新的内存地址。

## ARM64 Image 头不等于通用启动协议兼容

权威参考为 Linux v6.12 的 [ARM64 booting 文档](https://github.com/torvalds/linux/blob/v6.12/Documentation/arch/arm64/booting.rst)。该协议把偏移 8 定义为相对某个 2MiB 对齐基址的 `text_offset`，把偏移 16 定义为从 Image 起点计算的 `image_size`。本 shim 将这两个位置同时用作绝对 UEFI 地址及 FD 长度，源码自己称其为 `Fake Linux kernel header`。

这意味着它依赖原有 Samsung/Qualcomm 启动路径的具体行为，不能凭 magic 匹配认定通用 ARM64 loader 均能启动：

- `0x9FC41000` 并非通常意义上的小型装载偏移。
- 声明的 `image_size` 是 FD 长度，实际解压串为 `112 + FD长度`。不能把该字段当成整个解压 Image 的独立长度证明。
- Image flags 为零；没有 EFI PE/COFF stub，`res5` 为零。此 Android 启动镜像不是供任意 UEFI `LoadImage()` 直接加载的 PE 程序。

本轮没有改动这份历史启动约定。仅凭规范与静态分析，尚不足以证明改写头部能在精确的 SM-T733 rev 9 loader 上保持兼容。

## CPU、缓存和固件入口

shim 不使用栈，也不读取 `CurrentEL`、屏蔽中断、关闭 MMU、清理 D-cache、失效 I-cache 或执行复制后的 `dsb` / `isb`。它保留 x0，改写 x1–x6 后直接 `br x5`。

FD 中的 [PrePi 入口](../../Platforms/AndromedaPkg/PrePi/AArch64/ModuleEntryPoint.S#L15) 在进入后屏蔽中断、关闭 MMU/缓存并失效 I-cache/TLB。对应 ArmLib 的关闭函数包含屏障，但不等同于复制前后完整的 cache maintenance。更关键的是，必须先成功取到目的 FD 的指令，才能执行这些初始化，故下游 PrePi 不能倒推出 shim 的跳转已经缓存一致。

标准 Linux ARM64 入口约定要求 bootloader 提供 non-secure EL1/EL2、MMU off、正确的缓存清理、DAIF 等条件。这些条件只能作为与 Samsung loader 交接行为对照的依据，不能作为本设备的既成事实。贸然增加 cache / EL 控制指令也可能与具体固件状态冲突，本轮未这样修改。

## Android IMG 封装的实际语义

当前实际封装入口是根目录的 [PythonLibs/PostBuild.py](../../PythonLibs/PostBuild.py)，而不是历史描述中的 `Platforms/KodiakPkg/PythonLibs/PostBuild.py`。目标选择给出 `gts7fewifi.dtb` 后，它读取设备目录下 `DeviceTreeBlob/Android/android-gts7fewifi.dtb`。

逻辑仍为：

```text
kernel = gzip(BootShim.bin || SM7325_EFI.fd) || Android-DTB
boot.img = Android-v0-header + page padding + kernel + padding + dummy ramdisk + padding
```

`sm7325.json` 指定 header v0、4096 字节页、base 0、空 cmdline、OS 11.0.0、补丁日期 2023-04-01。附带的 `PythonLibs/emptyramdisk` 实际为 **6 字节 `dummy\n`**，并非零长度 ramdisk 或有效 Linux initramfs。

按照 [mkbootimg 默认值](../../PythonLibs/mkbootimg.py#L436)，这些参数会产生 `kernel_addr=0x8000`、`ramdisk_addr=0x01000000`、`tags_addr=0x100`。这些是镜像头字段，不能据此推断 Qualcomm loader 的实际物理放置位置。OS 元数据也不证明 Android 14 / rev 9 兼容，更不能绕过已锁定的 Verified Boot。

Python 3.12 的现有 `gzip.compress(payload_data,9)` 会默认写入时间戳，因此没有稳定时间控制时，重复封装哈希可能不同。历史哈希只能识别历史构建；与新构建不同不自动代表出错。

## 本轮最小修复及测试

在不修改汇编、设备地址、GPIO、DTB 或启动约定的前提下，修复了 [PostBuild.py](../../PythonLibs/PostBuild.py)：

1. 封装前检查 shim 的 ARM64 magic、目标基址/复制长度和 `build_cfg` 一致，复制长度为正且 16 字节对齐、入口 4 字节对齐且目的区间不溢出。
2. FD 必须精确等于 `UEFI_SIZE`。短 FD 会让 shim 读取其后的非 FD 数据；过长 FD 则不会被完整复制，均应在云端阻止生成候选镜像。
3. 关闭 payload 写入流后才调用 `mkbootimg`。原实现对小于写缓冲区的有效载荷可写出 **kernel_size=0** 的镜像；本轮以真实原版本运行回归用例重现该失败，再验证修复通过。
4. 校验失败发生在覆盖现有 `bootpayload.bin` 或创建新 IMG 之前；设备 `bootpack.json` 的 Android 头元数据 override 不改变编译目标的 BootShim 基址/长度要求。

执行结果：

| 检查 | 结果与范围 |
|---|---|
| `unittest discover -s Codex-Offline-Work/tests -p test_postbuild_validation.py -v` | 11 tests 全部通过；含短/长 FD、错误头、stale shim、无效长度/地址、有效压缩及非压缩封装、bootpack override |
| 原基础提交的小载荷回归 | 预期失败：实际 Android 头 `kernel_size=0`；此失败为修复证据，不是当前测试未解决失败 |
| `tools/bootshim_audit.py` | 当前机器码匹配，数据模型揭示正向重叠损坏；未模拟 CPU/缓存/loader |
| 全部 13 个 `build_cfg/*.json` 的范围/对齐约束 | 静态通过；不代表构建全部设备 |
| `git diff --check -- PythonLibs/PostBuild.py` | 通过 |

测试没有屏蔽 warnings。Python unittest 显示现有 `mkbootimg.main()` 未显式关闭 argparse FileType 流的 `ResourceWarning`；本轮未扩大改动至 AOSP helper，实际输出已经在函数返回后正确读取。

原始日志保留于 `/workspace/.cloud-setup/logs/postbuild-tests.log`、`postbuild-baseline-regression.log`、`bootshim-audit.json`。最终完整候选固件的结构、GZIP CRC、FD/DTB 对比、哈希和构建结果由主验证报告记录。

## 可复现命令

从仓库根目录执行，先激活已有本地工具链与虚拟环境：

```bash
source /workspace/.cloud-setup/toolchain-env.sh
source .venv/bin/activate
make -B -C BootShim UEFI_BASE=0x9FC41000 UEFI_SIZE=0x002BF000
python Codex-Offline-Work/tools/bootshim_audit.py
python -m unittest discover -s Codex-Offline-Work/tests -p test_postbuild_validation.py -v
```

`make -B` 是有意的：原 Makefile 没有把 UEFI_BASE / UEFI_SIZE 的变化作为依赖；切换设备后单纯 `make` 可能保留其他目标的旧 shim。原 `build_boot_shim.sh` 通过删除产物强制重建，但其错误传播不可靠，自动化脚本应检查实际命令退出状态。
