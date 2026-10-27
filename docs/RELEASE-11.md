# 多型号自动更新与云端交付验收

日期：2026-10-27。网页版本：20261027-3。机器可读证据：[release11-verification.json](release11-verification.json)。

## 已完成范围

- 与原站当前公开 overview 的 865 个 Kwrt 档案、24 个平台对应，固定网页快照全部通过配置、格式、平台身份和内容指纹审计。
- 22 个非 x86 平台的代表型号通过真实 ImageBuilder 构建、依赖及包清单检查、文件完整性和 SHA256 校验；x86 仍使用其独立的启动验收流程。
- 扩展 12 组真实设备/软件组合全部通过，覆盖 8 个平台，新增 7 个代表矩阵之外的型号。当前非 x86 共 29 个不同型号实际编译过；这不代表 865 个型号都已逐一编译或实机测试。
- N1 缺失校准包的兼容修复完成，新的验收版本可构建 sysupgrade；玩客云因上游校验值不一致继续暂停。
- 网页连接后读取私有验收目录和相应平台资料；当前配置、历史配置与新批准版本各自保留。逐文件下载保持原行为。

## 自动跟进的真实证据

[首次全平台流程 40442648609](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40442648609)：21 平台通过，两个上游问题明确标为暂停。

[N1 修复后流程 40443977840](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40443977840)：22 平台全部编译和校验通过，独立批准任务成功。当前多型号版本为 `kwrt-25.12-20261027-2f488046`，目录含 864 个非 x86 档案。另一个 x86 档案在独立版本内，总计 865；其中一个玩客云档案暂停，两个档案仅提供 ROOTFS。

[上游无变化复检 40445279846](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279846)：检测成功，`changed=False`、`required platform builds=0`；编译与批准任务均跳过，没有重复消耗完整构建分钟。

计划时间为 x86 每天 04:23、多型号每天 05:07（北京时间/新加坡时间，GitHub 可能延迟）。有变化的平台必须重新编译；没有变化的平台仅复用与资料及验证代码指纹一致的证据。任一活动平台失败、证据不完整、源中途变化或代码变化，都不会提升新版本。

构建任务仅有只读权限、不读取用户 Secrets。全新批准任务只校验数据、重查上游并原子提交 JSON，不提取或运行 ImageBuilder。历史构建器、目录和按哈希命名的元数据保留，分支不强制覆盖。

## 12 组扩展构建

| 型号 | 明确请求的软件组合 | 文件系统 | 实际结果 |
|---|---|---|---|
| GL.iNet GL-MT6000 | PassWall2、Xray、sing-box | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004890) |
| 小米 AX3000T | HomeProxy、sing-box | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004917) |
| 红米 AX6000 | OpenClash、mihomo | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004879) |
| NanoPi R2S | 文件管理、KMS、UU、TurboACC、NATMap | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004972) |
| NanoPi R5S | PassWall2、Xray、sing-box | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445785824/job/121997787033) |
| NanoPi R6S | Docker、Samba、硬盘休眠 | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445785824/job/121997787073) |
| 树莓派 4 | Samba、DLNA、Transmission、Aria2、硬盘休眠 | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445785824/job/121997786969) |
| 树莓派 5 | HomeProxy、sing-box | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004841) |
| 小米路由器 3G | DDNS、SQM、WireGuard、MosDNS | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004988) |
| 小米 AX3600 | HomeProxy、sing-box | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004863) |
| Linksys WRT3200ACM | OpenClash、mihomo | SquashFS | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004843) |
| Generic ARM64 | PassWall2、Xray、sing-box | Ext4 | [通过](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445279826/job/121995004875) |

首轮三组测试配置误选了上游未提供的 Ext4，均在准备阶段失败，未生成固件。已改用各自提供的 SquashFS，并增加调度前型号/软件/文件系统检查。[修正后三组复检 40445785824](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40445785824) 全部成功；其余九组在首轮通过。上述“12 组通过”指最终各自配置的成功结果，不将首轮失败任务改称成功。

测试固件不发布为用户下载，只保留三天诊断报告；本轮分别产生九份和三份报告。代理线路、Docker 容器运行、磁盘共享和无线收发没有被安装与文件校验代替。

## N1 修复依据与实际文件

Kwrt N1 导入的 iStoreOS 平台源码明确依赖通用 NVRAM 包；固定的 iStoreOS 提交 `283d02639c740f8ae6e9425b48be8c61f152c6b8` 明确定义了该包的链接和真实数据依赖。本项目只恢复这条链接，不编造校准参数，不删除无线依赖。详见 [N1-COMPATIBILITY.md](N1-COMPATIBILITY.md)。

真实 N1 编译得到 `kwrt-amlogic-meson-phicomm_n1-squashfs-sysupgrade.img.gz`，26,125,210 字节，SHA256：

```text
544609939f8e26fa6838e0a35ba5c99eef12e4d46393a80c7f75362eedf31fdf
```

包清单、ROOTFS 内链接及实际数据文件检查通过；gzip CRC 与 OpenWrt fwtool 尾部检查通过。未验证实体开机和 Wi-Fi 收发。旧固定版本保留原暂停状态，修复只进入新验收版本。

## 网页和部署修复

- 按需读取目标平台的私有元数据，对原始 UTF-8 字节执行 SHA256 和大小检查。资料损坏时不加载、不提交构建。
- 明确显示“此型号通过编译”或“同平台代表型号通过编译”，两者都不冒充实体启动。
- 切换最新验收版本保留所选软件、IP、主机名和待上传文件；切换型号会同步刷新升级入口，避免使用之前型号的入口。
- 刷新/重连后可恢复当前验收版本草稿；旧验收版本从历史目录恢复，不静默迁移到最新版。同日不同版本显示不同短哈希。
- 发现并修复网页部署对滚动软件索引的依赖。完整的 865 档案基线已纳入源码，部署仅做离线审计和指纹检查。上游更新不会阻止发布网站，验证失败不会替换现有 Pages。
- 本地浏览器使用真实云端验收数据的离线 API 重放检查授权、资料哈希错误和配置恢复；没有读取或保存用户的网页令牌。

## 代码检查与交付边界

JavaScript 71 项、Python 105 项，共 176 项。Windows 两项外部工具测试在 Linux CI 运行；Actions 工作流静态检查和全部设备配置审计通过。最终源码提交、CI、Pages 状态和备份哈希另存本轮交付 JSON。

用户暂时没有测试设备，按要求只完成云端范围。未刷机、未改家庭网络、未改 GitHub Secrets、未开通付费服务或新增长期凭据。root/root 保持用户明确要求的临时默认值。

玩客云现有构建器的公布 SHA256 为 `e29abe52fea3bdaf77a0af313ccb5c6f06c6564a4f7cdb27d41fd9215d6926b5`，实际下载为 `ebcf08047a5c586051f2f9e58a2485f3ada5c6c13f57b8441a187fc97e7400f0`。作者公开 Actions 的最新相关构建及产物元数据已检查，但没有把未经独立验证的二进制视为修复依据。仍需可信、与实际文件一致的发布资源；不会跳过校验。

任意内核/DTB 切换、实体 USB/WWAN/无线、真实代理线路和 ESXi 宿主机验收不包含在已完成范围。软件源没有完整归档，旧验收记录不保证上游永久保留相同软件；索引变化时旧版本的新构建会安全停止。

