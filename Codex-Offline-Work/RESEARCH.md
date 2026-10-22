# SM-T733 离线研究结论

对象严格为 **SM-T733 Wi-Fi / SM7325 / 6GB RAM / 128GB / CHN T733ZCS9DYE1 / Android 14 / locked bootloader rev 9**。本轮没有用 SM-T736、SM-T730、A52s 或其他设备的地址、GPIO、固件替换目标。

## 版本和启动路线

[上游核实](research/UPSTREAM-BOOT.md) 固定了本次读取的提交与证据。qaz6750 的 `xyz/sm7325/gts7fewifi` 仍为 `9e6cb5f1249d18bab50fecb614b4928f6ed55c8b`；`6ab400d2b11ca9727645ce8af11d72b56d562d20` 仅在其上增加 workflow。当前用户仓库来自更晚的 Aloha 主线，不能称为旧测试版原样复现。BootShim、目标静态内存映射、DSDT 和 Android DTB 与旧版一致，但 USB 二进制及公共框架已有变化。

最直接的机型先例是 Gezine 的 **SM-T733 Wi-Fi 6GB Android BOOT 镜像进入 EFI Shell**。其旧版本当时并未完成 UFS/USB/ACPI。当前 Aloha 封装仍属于这条容器路线，本轮实际构建和字节检查通过。DualBootKernelPatcher 没有 SM7325 配置，不为双启动套用其他设备 GPIO。

```mermaid
flowchart LR
  A[Samsung ABL / AVB 接受条件] --> B[Android boot v0 容器]
  B --> C[GZIP 解压 BootShim + FD]
  C --> D[BootShim 复制并跳转]
  D --> E[UEFI / ACPI / UFS / USB]
  E --> F[Windows Boot Manager 与驱动]
```

本轮验证了容器内容及构建，未证明左端的 locked rev 9 接受条件或后续硬件行为。SB/NOSB 是 UEFI 内部策略，不改变第一步的 Samsung 锁定状态。

## 低层审计与改动

[BootShim 审计](research/BOOTSHIM.md) 检查真实 112 字节机器码、复制循环、ARM64 Image 头和下游 PrePi。目标区间仍为 `[0x9FC41000,0x9FF00000)`；没有猜改地址、头部或缓存指令。正向复制对部分源/目标重叠会损坏数据，代码执行区覆盖、CPU 异常级别、MMU/cache 和实际解压位置均需硬件证据。

`PythonLibs/PostBuild.py` 增加封装前的一致性检查，并在 mkbootimg 重读 payload 前关闭写入流。原实现的小载荷 `kernel_size=0` 缺陷已用原版本重现；实际目标正常 payload 和失败路径均有回归测试。当前“emptyramdisk”实际为 6 字节 `dummy\n`，不是可用的 Linux initramfs。

[内存/ACPI 审计](research/MEMORY-ACPI.md) 分开考察静态图、RAM 分区协议、动态 GCD/页表添加路径和实际设备未知。对 `RamPartitionDxe.c` 只修复零余块、错误保存、数组越界和无效范围处理，保留所有地址与已有范围选择。后续分块在前块失败后仍会尝试，不能将此称为已解决全部 6GB 枚举。

Android DTB 声明约 4055MiB，Linux DTB 是空占位文件；没有用扩大 DTB memory 节点伪造 6GB 支持。固定 reservation 与 FD 无交集只是一项静态检查。通用 RAM bank 与 PEI 已注册区域的重叠、协议表的真实形状和动态保留内存仍需验证。

DSDT 校验及反汇编通过；将反汇编结果单独重新编译失败，具体输出及局限见 [验证记录](VALIDATION.md)。没有盲改 AML 或 signed driver 的硬件 ID。

## Windows 材料与判断

[Windows 与驱动清单](research/WINDOWS-DRIVERS.md) 固定 OEM/Yupik 版本，记录 170 个 INF 的 ARM64 声明、CAT 存在性、哈希、证书及缺失文件。OEM 套件已经包含平台驱动，不能无差别把通用套件再覆盖注入。存在测试证书、可选 provisioning 的 A52s 标识及需核对的 ACPI/INF ID；CAT 存在并不证明默认 Windows 信任链接受。

合法介质以 Microsoft Windows 11 ARM64 来源为起点，不能把历史 22621.1 的个案当作本机推荐版本或可继续支持的保证。尚未提供实际 ISO/WIM、许可与该固件的原厂 boot/vendor_boot/dtbo/vbmeta/PIT；对应真实内容检查和 Windows DISM/BCDBoot 操作未执行。只读检查工具和部署流程已准备，不能据此声称 Windows 启动就绪。

继续工作与设备边界见 [HANDOFF-TO-DEVICE.md](HANDOFF-TO-DEVICE.md)。
