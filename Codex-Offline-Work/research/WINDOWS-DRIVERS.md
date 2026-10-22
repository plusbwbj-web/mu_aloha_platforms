# Windows ARM64 与驱动准备记录

本记录针对 **SM-T733 / gts7fewifi / SM7325 / 6GB / 128GB / CHN T733ZCS9DYE1 / Android 14 / bootloader rev 9**。源码与二进制包检查不等于 Windows 已在此设备运行。没有连接设备，没有运行 DISM 注入、BCDBoot、分区、镜像写入或刷写。

## 固定版本与取得的材料

| 来源 | 实际解析的 HEAD | 角色与本次取得的证据 |
|---|---|---|
| [OEM 驱动](https://github.com/Project-Aloha/windows_oem_samsung_gts7fewifi/tree/9abbaab8bd658d81b300349961d116adb407a35c) | `9abbaab8bd658d81b300349961d116adb407a35c` | SM-T733 板级驱动、定制固件与扩展、桌面预置；30 个 INF 和对应 CAT；五个直接 OEM SYS 的 PE 架构检查 |
| [Yupik Silicon BSP](https://github.com/Project-Aloha/windows_silicon_qcom_yupik/tree/7fb2696f2337d3fa49a6bfd1adc526aa4cc2ebd4) | `7fb2696f2337d3fa49a6bfd1adc526aa4cc2ebd4` | Snapdragon 778G/778G+/782G 通用 SoC BSP；140 个 INF 和对应 CAT |
| [Microsoft Driver Docs](https://github.com/MicrosoftDocs/windows-driver-docs/tree/3aed2ca9f3624d431cba4e74b74e2e7284edf718) | `3aed2ca9f3624d431cba4e74b74e2e7284edf718` | Driver Store、签名、INF Manufacturer/TargetOSVersion 的官方源码文档 |

参考材料保留在 `/workspace/.cloud-setup/references/windows_oem_samsung_gts7fewifi`、`windows_silicon_qcom_yupik` 与 `windows-driver-docs`。两个驱动来源已完整检出，工作树与 Git 原始 blob 字节一致：OEM **300 文件**、Silicon **910 文件**；文件清单、字节数、Git blob ID 与 SHA-256 在 `driver-file-hashes.json`。这是本地来源缓存，没有装载或运行驱动；驱动没有复制到本仓库或提交到 Git 历史，原始 LICENSE 保留在来源仓库。`driver-manifest-oem.json`、`driver-manifest-silicon.json` 记录每个 INF 的版本、架构节、硬件 ID、CAT 路径和 SHA-256。证书解析记录在 `driver-catalog-certificates.json`。

## 已实际检查的项目

- 通过现有 HTTPS Git 认证读取两个驱动库，取得上述精确提交；未请求新 token。
- OEM **30/30**、Silicon **140/140** INF 有 `NTARM64` 模型节。两库每个 INF 声明的 CAT 都能在对应 Git 树中按 Windows 不区分大小写规则找到。
- 所有 OEM INF 的 SourceDisksFiles 文件名可在该 Git 树找到。这仅为名称清单检查，未宣称实现了 Windows 完整 INF 解析、驱动排名、CAT 成员哈希核验或 DISM staging。
- 实际读取五个 OEM SYS：`SM5714Battery.sys`、`WacomPenI2C.sys`、`SM5714Pmic.sys`、`FocalTechTouch.sys`、`PS5169.sys`，PE Machine 均为 **`0xAA64` (ARM64)**。各文件 SHA-256 见清单。
- 实际读取 Silicon `Drivers/` 下 **77 个 SYS**，PE Machine 均为 `0xAA64`。这不覆盖包内全部 EXE/DLL/固件的架构，也不证明驱动能在当前 Windows 签名策略下加载。
- 提取两个来源 CAT 中携带的 X.509 证书，并保留主体、签发者和日期；这不是 Windows Authenticode/内核代码完整性信任验证。
- 媒体检查器的 **8 项合成解析检查**通过：正常 PE、越界 PE、正常 WIM XML、越界 XML、UTF-16 INF、完整合成 ARM64 媒体树、拒绝 x64 EFI、拒绝 x64 WIM。**没有真实 Windows 安装介质可供检查**。

## 板级候选驱动版本

| 功能 | OEM INF | DriverVer | 静态集成条件 |
|---|---|---|---|
| 电池 | `Drivers/Battery/SM5714Battery.inf` | `08/11/2026,19.6.47.544` | `ACPI\SM5714F`；目标 AML 中存在相同字面 HID |
| PMIC | `Drivers/SM5714Pmic/SM5714Pmic.inf` | `08/11/2026,19.6.47.422` | `ACPI\SM5714P`；目标 AML 中存在相同字面 HID |
| S Pen | `Drivers/Pen/WacomPenI2C.inf` | `08/09/2026,21.43.21.203` | `ACPI\WCP9021`；目标 AML 未找到相同字面 HID/CID，仍需命名空间与运行时枚举核实 |
| 触摸 | `Drivers/Touch/FocalTechTouch.inf` | `08/09/2026,21.41.39.76` | INF 为 `ACPI\FT8203`，目标 AML 可见触摸 HID `STFT556A`；不能直接认为匹配 |
| Type-C 芯片 | `Drivers/TypeC/PS5169.inf` | `08/11/2026,19.6.14.181` | `ACPI\PS5169`；目标 AML 未找到相同字面 HID/CID |
| Wi-Fi / 蓝牙 | `Platform/Drivers/WLAN/Core/Gts7fewifi_wlan.inf` 与 BTFMUART_HSP | `06/12/2024,1.0.4056.4400` | 必须同时核实板级固件、ACPI 资源、GPIO/I2C/UART 与驱动依赖 |
| 显示/GPU | `Platform/Drivers/Graphics/DXKM/qcdx6490.inf` | `10/02/2025,30.0.4444.9300` | 含 `ACPI\VEN_QCOM&DEV_0A36` 及 REV 装饰；目标 AML 具有对应 QCOM0A36 字面 ID，REV 与资源仍需验证 |
| 音频 | OEM Platform Audio | `11/19/2024,1.0.1030.0000` | 需要 OEM ACDB/PIL/子系统固件与 ACPI 一致 |
| SoC 基础组件 | Silicon GPIO/I2C/PIL/PEP/XHCI/WatchDog 等 | 多数为 `06/12/2024,1.0.4056.4400` | 同属 SM7325 并不足以证明任意 OEM 板级配置兼容 |

以上 HID/CID 是静态字面值交叉检查，方法计算、别名或 `_CID` 运行时返回值尚未完整求值，不能据此断言实际设备必然不兼容。应结合 [MEMORY-ACPI.md](MEMORY-ACPI.md) 的 AML 审计，保留原始签名包，不能为“匹配”而直接改 INF 或移植其他设备的 GPIO。

## 已发现的具体限制

1. **CAT 存在不代表 Windows 默认信任。** 五个直接 OEM 驱动 CAT 含 self-issued `WDKTestCert XiaoYeZi`；140 个 Silicon CAT 均携带社区 `WoA msmnile` 证书链。OEM 其他包中有 18 个相同社区链、4 个 Miatoll、2 个 Microsoft 链；GPU CAT 没有通过当前 PKCS#7 证书提取器取得证书数据。这里只检查证书容器，没有验证当前 Windows 根信任、吊销、时间戳、内核策略或目录成员完整性。即使带 Microsoft 名称，也不能据此宣称签名验证通过。下一阶段需要 Windows SDK SignTool/Code Integrity 逐包核验，并确定合法且适当的开发签名策略；本次没有执行任何关闭签名强制或自动信任证书的操作。
2. Silicon 的 `Extensions/Camera/AuxiliarySensor/qccamauxsensor_extension7280.inf:52` 声明 `SCFG_AUX_QRD.bin`，其文件名在精确提交的整个 Git 树中不存在。相机 README 也明确列为未工作功能；不要对整个 BSP 无选择地 `/Recurse` 注入并把该组件算作已准备完成。没有修改上游签名 INF/CAT。
3. OEM 已包含 `Platform/Drivers` 与 `Platform/Extensions` 板级覆盖，不能把它与 Silicon 库直接覆盖合并。必须按硬件 ID、ExtensionId、版本、资源与依赖选择包，保留来源和原始字节。
4. OEM `Setup/DesktopSetup/Device.json` 的 `shortSku` 仍为 `A52s`；`Settings/Gts7fewifi_DeviceInfo.inf` 使用 `ROOT\A52s_DeviceInfo` 名称。DesktopSetup INF 会复制 Unattend、OOBE PowerShell、桌面设置等，属于系统定制，不是 UFS 启动的前提。本阶段不采用 `Setup/`、桌面身份或 OOBE 模板。名称问题不能通过修改签名包“顺手修好”。
5. OEM README 当前将 Wi-Fi、触摸、音频、UFS 等标为可用，但没有给出此 **6GB/128GB、CHN rev 9** 设备及相同 UEFI/Windows 版本的测试矩阵；GPU 仍提到显示异常，TPM 为未知，相机/内置麦克风等为未工作。这是维护者状态说明，不能替代本机测试。
6. Silicon LICENSE 包含 Surface Duo 固件仅允许用于 Surface Duo 的条款，并保留 Qualcomm 专有权利声明。无法仅从仓库概括许可确认全部固件可以再分发给 SM-T733；因此本交付提供原始来源与清单，没有重新打包、再分发或安装有来源限制的固件。

一个正面静态结果：OEM `Platform/Extensions/HexagonLoader/PIL/Gts7fewifi_pilext.inf:75` 的 PGCM BaseAddress `0x84700000`、Size `0x19500000` 与目标 UEFI 的 `PIL Reserved` `[0x84700000,0x9DC00000)` 完全一致；ADSP/CDSP/VENUS/EVA/IPA 地址也对应所选 Android DTB 固定区。通用 BSP 文档的 IDP/QRD 地址计划则不同。因此应使用具体 OEM 配置继续集成，但此一致性不能证明运行时固件加载、内存生存期或 Windows 启动已验证。

## Windows 版本与合法介质

微软公开 ARM64 安装介质入口为 [Windows 11 for Arm-based PCs](https://www.microsoft.com/en-us/software-download/windows11arm64)。本云网络访问 `www.microsoft.com` 与 `learn.microsoft.com` 均收到 **CONNECT 403**，因此未下载 ISO、未核验当前入口选择的版本、语言或官方 SHA-256，也未取得用户 Windows 许可证。

可用的准备路线是取得具有相应授权、微软原始来源的 ARM64 ISO，保留网页公布哈希与下载时间，再检查提取后的 EFI 和 WIM/ESD 架构。不要从其他设备包或未明镜像站获得“预激活”Windows。历史 `22621.1`（22H2）桌面案例只用于复现研究，不作为 2026 年日常联网系统的推荐版本。当前源码与驱动资料不足以确认某个受支持 Windows 11 版本已经在本设备完整验证；不能凭 INF 最低 build 装饰选定“最稳定版本”。

只读校验工具：

```bash
python Codex-Offline-Work/tools/check-windows-media.py self-test
python Codex-Offline-Work/tools/check-windows-media.py media /path/to/extracted-arm64-media
python Codex-Offline-Work/tools/check-windows-media.py drivers /path/to/pinned-driver-checkout
python Codex-Offline-Work/tools/check-windows-media.py source-hashes /path/to/pinned-driver-checkout
```

媒体检查要求 `EFI/BOOT/BOOTAA64.EFI` 的 PE Machine 为 ARM64、PE32+、EFI_APPLICATION 子系统，`sources/boot.wim` 和 `install.wim` / `install.esd` 的 WIM XML 每个 image 的 ARCH 为 12。它验证边界、数量和架构；没有实现 WIM 全资源解压/校验、微软签名验证或 ISO 来源证明。压缩 XML、split SWM 需要官方 DISM 或经过信任验证的 wimlib 继续检查；工具会报告尚未完成而不判为通过。可在 Windows PC 上先只读运行 `DISM /Get-WimInfo /WimFile:<实际路径>` 选择名称/架构正确的 image index，不能假定 index 1。`source-hashes` 可复核检出文件没有字节变更；本次重跑该命令，再次复现了全部 300 个 OEM 文件的清单与哈希。

## 后续电脑端部署顺序（本次未执行）

1. 在受支持的 Windows PC / 合适版本 ADK 中，对已获授权 ARM64 安装介质建立可丢弃的离线副本。先核实 ISO 哈希、WIM image index、ARM64 架构和 Windows 版本。
2. 从 UEFI 输出与 ACPI 获取设备清单，制作最小的板级驱动选择清单。先处理启动所需 HAL、总线、存储、PEP、计时和输入，再逐项加入 GPU、无线、音频与固件。泛用 BSP 的 PIL 地址规划必须与目标 UEFI 保留区和 OEM 扩展一致，不能复制 QRD/IDP 文档地址当成 SM-T733 结论。
3. 使用 Windows 官方 SignTool/Code Integrity 检查所选包的目录签名、成员哈希与信任要求；缺文件、硬件 ID 不匹配、未授权固件和签名策略问题解决前，不注入整库。保留原 INF/CAT 编码和原始字节，不使用 `/ForceUnsigned` 掩盖问题。
4. 以后在明确的离线镜像目录使用 DISM 安装已确认的单个 INF，并保存完整日志；`DISM /Image:<离线根目录> /Get-Drivers /All` 可读取结果。执行注入会修改离线副本，本次未执行；更不指向真实平板磁盘。
5. 分区与实际盘符/卷 GUID 要到获得设备授权、确认备份与恢复路线后再制定。Windows 目录、ESP 和恢复分区均不能用历史 `/dev/block/sda*` 或固定盘符推断。
6. 使用匹配目标的 Windows 工具和实际离线 Windows 根目录建立 UEFI 启动文件；BCDBoot 会写入指定 ESP，故本次不执行。以后需检查 `EFI/Microsoft/Boot/bootmgfw.efi`、必要的 `EFI/BOOT/BOOTAA64.EFI` 与 `Windows/System32/winload.efi` 均为 ARM64，并以 `bcdedit /store <实际BCD路径> /enum all` 核查 device/osdevice。复制 EFI 文件本身不证明存储驱动、BCD、ACPI、内核或签名策略已满足。
7. UEFI 的 SB/NOSB 构建选项、三星 OEM 解锁/AVB 状态以及 Windows 内核驱动信任属于三个不同条件。任意一个成功不意味着另两个已满足；locked 三星 bootloader 不能因为 Windows 驱动或 UEFI 内部签名存在就执行未授权镜像。

## 真机阶段仍需验证

先确认型号、RAM/存储实际枚举与准确固件 build，保持完整备份和可用的同版本恢复材料；然后只在用户重新授权后执行设备操作。首次进入 UEFI 需保存实际 Memory Map、RAM 分区表、ACPI、UFS LUN/分区标识、USB枚举和日志。Windows 首次启动后记录 `msinfo32`、可用 RAM 与保留区、Device Manager 硬件 ID/错误码、Code Integrity / Kernel-Boot / PnP 日志、存储读写、温度/充电/电池、触摸/笔、USB、Wi-Fi、蓝牙、GPU、音频和休眠恢复；不把 6GB RAM 标称容量或 README 的绿色图标当作本机验收。

## 官方参考

- 已实际读取的 Microsoft 官方源码：[Driver Store](https://github.com/MicrosoftDocs/windows-driver-docs/blob/3aed2ca9f3624d431cba4e74b74e2e7284edf718/windows-driver-docs-pr/install/driver-store.md)、[Driver Signing](https://github.com/MicrosoftDocs/windows-driver-docs/blob/3aed2ca9f3624d431cba4e74b74e2e7284edf718/windows-driver-docs-pr/install/driver-signing.md)、[INF Manufacturer](https://github.com/MicrosoftDocs/windows-driver-docs/blob/3aed2ca9f3624d431cba4e74b74e2e7284edf718/windows-driver-docs-pr/install/inf-manufacturer-section.md)。Driver Store 文档明确要求受信任目录签名以及 INF 和全部引用文件。
- 未能从当前网络读取的官方操作参考：[DISM driver servicing](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/dism-driver-servicing-command-line-options-s14)、[BCDBoot](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/bcdboot-command-line-options-techref-di)、[ADK](https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install)。后续执行前应核对对应当前 ADK/Windows 版本的官方文档。
- 板级状态与来源许可：[OEM README](https://github.com/Project-Aloha/windows_oem_samsung_gts7fewifi/blob/9abbaab8bd658d81b300349961d116adb407a35c/README.md)、[OEM LICENSE](https://github.com/Project-Aloha/windows_oem_samsung_gts7fewifi/blob/9abbaab8bd658d81b300349961d116adb407a35c/LICENSE.md)、[Silicon README](https://github.com/Project-Aloha/windows_silicon_qcom_yupik/blob/7fb2696f2337d3fa49a6bfd1adc526aa4cc2ebd4/README.md)、[Silicon LICENSE](https://github.com/Project-Aloha/windows_silicon_qcom_yupik/blob/7fb2696f2337d3fa49a6bfd1adc526aa4cc2ebd4/LICENSE.md)、[PIL 内存配置说明](https://github.com/Project-Aloha/windows_silicon_qcom_yupik/blob/7fb2696f2337d3fa49a6bfd1adc526aa4cc2ebd4/docs/PIL.md)。
