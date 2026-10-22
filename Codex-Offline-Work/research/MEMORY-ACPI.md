# SM-T733 内存、ACPI、UFS 与 USB 审计

审计对象：`81e4762094f338573d39f9d31bcdcff5e924ad7d` 基础上的
`codex/sm-t733-offline-prep` 工作分支，设备目录严格为
`Platforms/KodiakPkg/Device/samsung-gts7fewifi`。这是源码和离线文件审计；没有读取真实平板的 RAM 分区、UEFI Memory Map 或 Windows 设备状态。

## 已执行检查

| 检查 | 实际结果 | 证据 |
|---|---|---|
| Android DTB 结构解析 | 通过；FDT v17，652,519 bytes，包含 131 个合法 FDT_NOP | `../logs/memory-audit.json` |
| UEFI FD 与 DTB 固定保留区相交检查 | 未发现相交 | 同上；这不是动态内存安全证明 |
| 设备 DSDT 长度、校验和 | 83,917 bytes，声明长度一致，8 位和为零 | 同上 |
| 12 张选中 ACPI 表长度 | 全部与文件一致；FACS 无普通表校验和 | 同上 |
| DSDT 反汇编 | IASL 20250404 返回 0；存在 1 个未解析外部控制方法 | `../logs/acpi-disassemble.log` |
| 将反汇编 DSL 原样重新编译 | **失败**：19 errors、44 warnings、313 remarks，未生成替代 AML | `../logs/acpi-recompile.log` |
| 修改后的实际 RamPartitionDxe C 主机测试 | **15 个用例通过**，GCC + AddressSanitizer + UndefinedBehaviorSanitizer | `../logs/ram-partition-test.log` |
| 基础提交的 4GiB 拆分回归 | 预期失败，进程 abort；返回值不为成功 | `../logs/ram-partition-baseline-failure.log` |

重现：

```bash
cd /workspace/mu_aloha_platforms
.venv/bin/python Codex-Offline-Work/tools/memory_audit.py \
  --output Codex-Offline-Work/logs/memory-audit.json
.venv/bin/python Codex-Offline-Work/tools/test_ram_partition.py
```

`memory_audit.py` 使用只读标准库解析器，检查文件边界、FDT 标签、reg 单元、内存范围和 ACPI 表头，不依赖运行中的设备。仓库指定的 `fdt==0.3.3` 对这个 DTB 的合法 FDT_NOP 标签报 `Unknown Tag: 4`，因此没有把该库的解析失败当作 DTB 损坏。

## 4055MiB DTB 与 6GB 的差别

Android DTB SHA-256：

`5b2978ee329b9292fd336d479c3bafdeadc4c4190965d80932c9ee655c8ef7f1`

根节点 model 为 `Samsung GTS7FEWIFI PROJECT (board-id,02)`；compatible 为
`qcom,yupik-idp`, `qcom,yupik`, `qcom,idp`。`/memory/reg` 的全部范围如下，右端不包含在范围内：

| 起点 | 终点 | 大小 |
|---|---|---:|
| `0x80000000` | `0xBB900000` | 953MiB |
| `0xBBF00000` | `0xBDD00000` | 30MiB |
| `0xC0000000` | `0x100000000` | 1024MiB |
| `0x100000000` | `0x180000000` | 2048MiB |
| 合计 | | **4055MiB** |

DTB 还包含 35 个固定 reserved-memory 条目和 11 个动态 size-only 条目；零长度条目单独保留，不当作实际相交区域。动态保留区的最终落点、Samsung 启动器对 DTB 的修改、SMEM 的真实内容都不能由此文件推导。

`DeviceTreeBlob/Linux/linux-gts7fewifi.dtb` 是 **0 字节占位文件**，未验证为可用的 Linux DTB；当前 Android Boot Image 封装选择的是非空 Android DTB。

不能把 memory/reg 扩到 6GB 来替代实际 RAM 检测。这会把未知或不存在的地址交给内存分配器，且不能证明安全世界、显示、PIL 和 Bootloader 的保留要求已经满足。

## UEFI 静态映射与高地址 RAM 路径

关键源码路径：

- `Platforms/KodiakPkg/Device/samsung-gts7fewifi/Library/PlatformMemoryMapLib/PlatformMemoryMapLib.c:10-78`：静态 DDR 区域，最后一段默认到 `0x180000000`，覆盖从 `0x80000000` 开始的 4GiB 物理跨度，包含多个不可用或保留区域；注释所称 8GB 不是已映射 8GB 的证据。
- `Platforms/AndromedaPkg/MemoryInitPei/MemoryInitPeiLib.c:43-54,81-129`：根据上述表生成资源/分配 HOB，并使用相同地址作为 VA 和 PA 初始化 ARM MMU。
- `Platforms/AndromedaPkg/Library/ArmPlatformLib/ArmPlatformLibMem.c:29-67`：同样使用 64 位物理地址/长度构造恒等映射。
- `Platforms/QcomModulePkg/Include/Protocol/EFIRamPartition.h:62-65`：RAM 分区基址与长度均为 `UINT64`，接口本身能表达超过 4GB 的物理地址。
- `Platforms/AndromedaPkg/Driver/RamPartitionDxe/RamPartitionDxe.inf`：驱动依赖 `gEfiRamPartitionProtocolGuid`，不会仅凭文件存在就运行成功。
- 设备 `DXE.inc:7`、`APRIORI.inc:17` 和 `DXE.dsc.inc`：将该驱动纳入构建。
- `MU_BASECORE/UefiCpuPkg/Library/ArmMmuLib/AArch64/ArmMmuLibCore.c:617-644,676-781`：动态更新页表；初始化按 CPU 实际物理地址位数选择 TCR 地址能力，并非硬编码 32 位地址上限。

RAM 协议 GUID 的字节序列能在该设备的 `EnvDxe.efi` 和 `QcomBds.efi` 中找到。这是二进制引用证据，不能单独证明哪一个模块提供协议、返回何种内容，或当前 rev 9 启动链一定能提供它。

`RamPartitionDxe` 尝试通过协议获得分区，再给高于 `0x180000000` 的区域添加 GCD SystemMemory、ARM 页表属性和 EFI_MEMORY_WB 属性。该路径存在，仍不等于 6GB 实机成功。尤其应检查：

1. 返回的分区形态。如果一个分区从 `0x80000000` 连续覆盖全部 RAM，现有 generic-base 分支先对 `0xA0000000` 以后的整个范围执行 AddMemorySpace，然后 continue；这与已经注册的低地址范围重叠，而且不会进入后面的高地址裁剪分支。若固件返回独立高地址分区，代码路径不同。没有真实协议输出，不能选择一种布局代替另一种。
2. 原始低 DDR 分支的 GCD 添加可能与静态 HOB 重叠并返回错误；本次修复会报告错误，同时仍尝试其余分区。需要真实日志区分“已存在”与错误映射，不能据主机 mock 的成功声称该路径正确。
3. `KodiakNoSb.dsc:65` 和 `Kodiak.dsc:65` 的 `PcdSystemMemorySize` 为 8GB。它不是安装 RAM 的检测结果；当前 MemoryPeim 主要用静态描述表建 HOB。其他 fallback 消费者必须与运行时证据一起检查。
4. `Silicon/QC/Sm7325/QcomPkg/Library/AcpiPlatformUpdateLib/AcpiPlatformUpdateLib.c:64,172` 将 ACPI `SDDR` 元数据写成 4。此 DSDT 内只见该名称定义，未见 AML 内部对 SDDR 的其他使用；不能仅凭这个字段认定 Windows 内存上限被固定为 4GB，也不能把它直接改为 6 当作适配完成。

## FD、BootShim 与保留范围

`build_cfg/sm7325.json` 和 `Platforms/KodiakPkg/Kodiak.fdf:23-28` 一致：

- FD 基址 `0x9FC41000`，长度 `0x002BF000` = 2,879,488 bytes。
- 区间 `[0x9FC41000,0x9FF00000)`，4KiB 对齐，长度是 16 的整数倍。
- 静态 `UEFI FD` 区域为 `[0x9FC00000,0x9FF00000)`；整个 FD 在其中。
- 紧邻其后的 SEC Heap、CPU Vectors、MMU PageTables、UEFI Stack，以及日志/信息块分别有静态类型。FD/Heap/Stack 多为 BootServicesData，日志/Info 为 RuntimeServicesData；这与 Windows 接管时的可回收/持久内存语义有关，不应简单把所有 reserved 区改成 ConventionalMemory。

本次没有修改这些地址或内存类型。BootServicesData/LoaderData 等区能否在 ExitBootServices 后回收，要服从实际 UEFI Memory Map；真正运行中的 RuntimeServices 区应继续保留。必须另行获取 EFI Shell `memmap`、协议 RAM 表和 Windows 可见物理内存，才能确认 6GB 型号完整且正确的内存交接。

固定 DTB 保留区与 FD 无相交只解决一个小范围问题。审计还发现 **静态 ConventionalMemory 与 Android DTB 固定保留区有交叠**，例如 `pil_trustedvm_region`、qrtr/neuron、Samsung 日志/ramoops，以及部分低地址区域。两套表服务于不同启动环境，可能存在有意回收；没有 live firmware/SMEM/保留区生命周期的证据，不能把这些交叠一概判为可用内存或直接删除保留。完整列表在 JSON 的 `conventional_vs_android_fixed_reservation_overlaps_require_review`。

静态表自身的潜在问题也保留为限制：

- 默认分支 `Reserv [0xC0000000,0xC1000000)` 与 `TAGS [0xC0100000,0xC1300000)` 相交。两项都是 NoHob、相同 Device 属性，需核实原始平台布局。
- IMEM Cookie 位于 IMEM Base 范围内、USB/AOSS 大 MMIO 窗口相交；不能仅用几何重叠推断寄存器映射错误。
- `USE_MEMORY_FOR_SERIAL_OUTPUT=1` 时，PStore `[0xE4B00000,0xE4F00000)` 与下一 RAM Partition 从 `0xE4B40000` 开始相交。当前 SB/NOSB DSC 均将此选项设为 **0**；不要开启该选项后当作已经验证的调试方案。本次未猜测修改其地址。

## 本次最小源码修复

仅修改顶层仓库的 `Platforms/AndromedaPkg/Driver/RamPartitionDxe/RamPartitionDxe.c`，未修改依赖子模块，未改变内存地址、GPIO、SoC 配置或 DTB。

- 将拆分逻辑改为每次最多 2GiB、仅在剩余长度非零时添加。基础版本在长度恰好为 4GiB 等倍数时，最后调用 `AddRamPartition(...,0,...)` 并返回 EFI_INVALID_PARAMETER。
- 拆分中保留首个添加失败，同时继续尝试后续块，避免后续成功覆盖早先失败，也保留原版对后续高地址块的尝试。单个连续 6GiB bank 首块与低地址 GCD 重叠的回归用例已覆盖；这不会修复尚需设备证据的范围划分问题。
- 拒绝零长度与 64 位地址加法溢出，以及低区域裁剪下溢。
- 在写入扩展描述符**之前**用实际 9 元素数组容量检查边界，避免原有先越界写、后用无关的 128 元素上限断言。
- 按实际填充条目数量遍历，允许全部 8 个扩展槽被使用时不越界读取不存在的零终止项。
- 初始化保留首个添加失败，继续尝试其他条目，最后返回该错误；不再无条件报告初始化成功。分区选择和裁剪规则维持原样，因此上文布局风险仍待设备证据。

`test_ram_partition.py` 从当前 C 文件读取实际函数实现，仅替换 UEFI 头文件和服务为主机 mocks，执行 15 个真实编译后的 C 测试：零/溢出输入、2/4/6GiB 拆分、首个错误及继续后续块、协议不存在、8/9 条扩展分区容量、低范围下溢、清理、跨条目错误报告和单个连续 6GiB bank 的初始添加失败。ASan/UBSan 没有报告错误。它不是硬件模拟器，也不能验证 GCD/CPU 实际行为。

## ACPI 已知限制与 Windows 条件

该目标选择设备专用 `ACPI/DSDT.aml`，其余 MADT/CSRT/DBG2/FACP/FACS/GTDT/IORT/MCFG/PPTT/SPCR/TPM2 来自固定子模块的 `SurfaceDuoACPI/7325/builtin`，具体清单由 `KodiakPkg/Include/ACPI.inc` 决定。DSDT 表头 OEM ID `QCOMM`、Table ID `SDM7280` 是文件实际内容；不能单凭此名称把它当作当前 SM-T733 6GB/rev 9 的验证结论。

9 张上游 raw ACPI 表的 checksum 字段为零，静态求和不为零。最初的严格原始文件校验因此失败，调查后确认 `AcpiPlatformDxe/AcpiPlatform.c:213-224` 在安装前重新计算校验和，`AcpiTableDxe/AcpiTableProtocol.c:242-250` 也以 Checksum=TRUE 安装。审计脚本保留全部原始 checksum warnings，检查声明长度和设备 DSDT 校验和，但**没有改写这些上游表**。运行时已安装表的校验和尚未验证。

反汇编后的 DSL 原样重编译失败并不阻止现有构建嵌入原始 AML，但说明这里不是可重复重建且严格通过当前 IASL 的 ACPI 源码。19 个错误包括 `_DEP` 中的 String、`_CLS` 的 Integer、NFCD/MBCL 等缺失名称，以及 SM5714F/SM5714P/SECHWN/646YD01 的 HID 格式问题。缺失名称可能涉及其他运行时 namespace；现有 OEM 驱动还使用其中一些非标准 ID。没有完整 namespace 和设备验证前，不应为了编译通过而删除对象、改变 HID 或从其他设备替换 AML。

静态 driver-ID 交叉检查：目标 DSDT 含 `SM5714F`、`SM5714P`、`QCOM0A36`，与 OEM 电池、PMIC、显卡驱动 ID 有对应；未在字面量 HID/CID 中找到笔的 `WCP9021`，目标触摸 HID 为 `STFT556A`。这种字符串匹配不是完整 AML 求值或 Windows PnP 匹配，仍需检查 `_STA`、别名、资源、依赖和 Windows 实际设备实例。

Windows ARM64 的基本前提仍包括：正确的 MADT/GTDT/GIC/PSCI、ACPI namespace/资源、IORT/SMMU DMA、运行时服务、UEFI Memory Map、存储控制器与启动盘、以及匹配且可被目标 Windows 信任的驱动。没有 SRAT 并不自动意味着无法识别 RAM；Windows 接收的 EFI Memory Map 才是关键输入之一。

设备 OEM 驱动 `windows_oem_samsung_gts7fewifi@9abbaab8bd658d81b300349961d116adb407a35c` 中 `Platform/Extensions/HexagonLoader/PIL/Gts7fewifi_pilext.inf:75-76` 的 PGCM 基址 `0x84700000`、大小 `0x19500000` 与设备静态表的 `PIL Reserved [0x84700000,0x9DC00000)` 完全一致；ADSP/CDSP/VENUS/EVA/IPA 基址也与 Android DTB 的对应固定区域一致。这比通用 Silicon 驱动文档的其他板型地址更直接，但仍只是配置交叉检查，没有验证 PIL 加载、释放和 DMA 生命周期。

## UFS 与 USB 的静态证据

- 设备 DXE/APRIORI 包含自己的 `PatchedBinaries/UFSDxe`、USBConfig、UsbInit、UsbDevice、UsbfnDwc3、XHCI 等模块；不是拿 A52s 的二进制直接替代。
- UFS 驱动是 PE32 预编译模块，INF Depex=TRUE。本次能检查存在性、所选路径及 PE 架构，无法对闭源初始化和 rev 9 firmware API 做完整源码审计。
- 平台配置开启 `EnableUfsIOC=1`、`UfsSmmuConfigForOtherBootDev=1`、`UEFIExitUfsSSURequired=1`。这些是配置，不是 UFS I/O 测试结果。
- DSDT 有 UFS0，HID `QCOM24A5`、MMIO `0x01D84000`，可用性取决于 STOR；平台 ACPI 更新设置 STOR=1，并尝试读取 UFS 规格版本更新 PUS3。
- DSDT 含 USB0/UFN0/USB1、USB/TypeC 依赖；`MsPlatformDevicesLib` 触发 USB 初始化事件。驱动存在不能证明 VBUS、TypeC 方向、Hub、存储或键鼠在真机正常。

后续真实设备阶段应先以只读信息收集确认精确固件、解锁资格及备份方案，再在单独授权的启动测试中记录 RAM 协议、完整 `memmap`、ACPI dump 和设备枚举。此文不包含任何刷写或磁盘修改操作。
