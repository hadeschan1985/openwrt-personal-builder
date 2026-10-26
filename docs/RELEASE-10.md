# 全设备目录与平台构建完善记录

日期：2026-10-26 至 2026-10-27。网页版本：20261027-1。

## 设备范围与真实状态

读取原站公开 overview、各目标 profiles、包索引和 ImageBuilder 校验文件，逐一比对 (target, profile) 身份；匹配 865 个设备档案、24 个平台。没有向原站提交构建，也没有读取其登录凭据。

全部档案已通过配置及格式审计。863 个档案可进入构建流程，其中两个仅提供 ROOTFS；另两个档案明确暂停：
- amlogic/meson 的 N1：默认 brcmfmac-nvram-43455-sdio-generic 无法从当前源安装，未随意删除无线校准依赖。
- amlogic/meson8b 的玩客云：公布 SHA256 e29abe52fea3bdaf77a0af313ccb5c6f06c6564a4f7cdb27d41fd9215d6926b5，实际 310094706 字节构建包 SHA256 ebcf08047a5c586051f2f9e58a2485f3ada5c6c13f57b8441a187fc97e7400f0。下载未执行，不跳过校验。

非 x86 真实构建采用每个平台一个代表型号，先覆盖平台通路，再保留每次实际构建的文件校验结果。目录审计、代表型号编译、虚拟机引导、实体硬件测试是不同层次；没有声称 865 台实机均已测试。

首轮平台回归：40334387288；修复后的失败项目回归：40337025092。21 个非 x86 平台的代表型号全部通过编译和文件校验；两个明确暂停的平台保留失败证据。

[x86 构建 #8](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40376998386) 的 EFI、Legacy、EFI VMDK、Legacy VMDK 均实际启动、root 密码登录及配置验收通过，生成四个独立 ZIP，分别约 74 MB；使用临时 root / root，没有依赖用户 Secret。

[红米 AX6000 构建 #9](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40377441873) 额外加入 HomeProxy、curl、DDNS，factory 与 sysupgrade 分别编译、校验及上传成功；约 33 MB 和 31 MB。其状态明确为未做实机启动测试。

新包索引变化已通过 [自动上游回归](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40337451276) 批准；该流程完成官方与 Kwrt 六种引导/后台登录检查。另一次基线引导回归 40334387707 也通过。

## 实现与修复

- 原有 x86 固定版本兼容结构保留，新增 23 个分别固定校验值的构建器；玩客云单独识别版本化路径和 profiles.json.b。
- 各设备自己的 SquashFS / Ext4、sysupgrade / factory / SD / EMMC / ROOTFS 输出；x86 专属开关在其他型号禁用。
- 每个设备固件独立上传，最多 32 文件；不再把其他平台全部固件捆成一包。
- ath79、MT7621 移除源中已下架的可选 autocore；RISC-V 同时移除已下架的可选 luci-app-fan。内核和关键驱动未自动删除。
- gzip 验证支持 OpenWrt fwtool 尾部，并分别验证压缩数据 CRC、尾部 CRC 和整体 SHA256；不把合法尾部误判为损坏，也不忽略未知尾部。
- Kwrt ROOTFS 中仍检查中文资源实际存在；自订 IPK 按所选设备架构检查，仍在设备端安装。
- 新配置显式选择临时 root 密码；旧配置导入保持原有语义。未读取或覆盖用户 Secrets。
- 401 清除页面令牌并停止请求，403 权限错误停止轮询；429 / 403 限流遵守响应时间并退避，多次失败暂停。不会自动重试有写入效果的提交。
- 中文品牌和多个搜索词、页面缓存版本、当前使用说明一并更新。

## 验证和边界

代码测试为 JavaScript 66 项、Python 88 项。配置审计覆盖全部 865 档案；实际 ImageBuilder 与虚拟机回归在私有 Actions 执行。线上目录已核对 865 档案、24 平台；网页测试覆盖中文搜索、ARM64 选包、多种格式、ROOTFS 专用档案、暂停设备、授权失效和限流停止请求。云端结果及下载校验值另见本轮 JSON 证据。

N1 的上游预编译 ROOTFS 也已按公布 SHA256 验证并只读检查，其中未找到缺失的 43455 NVRAM 校准文件，未从其他设备借用校准数据。

自动批准更新仍覆盖 x86/64；新增其他平台使用构建器与软件索引指纹，检测到变化即暂停，尚未实现全平台更新自动批准。没有改动家庭网络、刷机、删除历史固件或扩展账户权限。

主要格式依据：[OpenWrt fwtool](https://github.com/openwrt/fwtool)，限流处理依据：[GitHub REST API 限流说明](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)。
