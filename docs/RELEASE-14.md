# 软件收尾与逐型号补测 · 2026-10-28

本轮在第 13 轮基础上继续处理玩客云上游索引失效、扩大逐型号实际编译，并复查四个盒子缺失资源。继续使用 GitHub Pages + Actions，没有增加 VPS、收费服务或会员功能。

代码检查 [40628258796](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40628258796) 确认 JavaScript 85 项、Python 165 项，共 250 项，Linux 零失败、零跳过。新读取规则的四项测试还覆盖错误地址、错误平台、服务器错误、不完整索引、并发发布文件变化及异常后恢复；原编译文件摘要继续保持不变。后续添加的独立云端诊断不改变构建或批准规则。

## 玩客云更新恢复

原站的 `packages-25.12/arm_cortex-a5_vfpv4-index.json` 返回 404，但原来的七份 IPK 软件源索引均可读取。更新流程仅在这个准确目标和准确 404 情况下，切换到构建器本来支持的原始 IPK 索引读取方式；仍使用原构建器、原软件源和原作者缓存身份。其他地址、平台、服务器错误或不完整索引不会触发替代。

- [全目录真实读取 40626117781](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40626117781)：23 个非 x86 平台、864 个档案资料完整，玩客云七份索引包含 11,033 个包，两次读取摘要一致。
- [实际玩客云编译 40626718014](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40626718014)：重新取得作者仍公开发布的原始构建器，核对原 ZIP 和构建器 SHA256；使用临时测试配置生成真正的 USB-burn 镜像，校验 Gzip、Amlogic 容器 CRC，并将 boot/rootfs 分区转回后逐一核对长度和摘要，全部通过。
- 此公开测试没有读取或上传私有配置、用户文件、令牌或私有来源缓存，只保存报告与日志；没有上传测试固件，没有生成新的私有批准记录，也没有实机启动结论。
- 更新批准仍要求平台实际编译及前后软件源复查。并发分支检查额外绑定新读取规则和工作流的准确文件内容，重试时同样检查，不覆盖历史批准。

实际镜像为 `kwrt-amlogic-meson8b-thunder-onecloud-ext4-emmc_burn.img.gz`，21,720,248 字节，本次 SHA256 为 `2c8ab3f7d0f524bad3640dc0deb58ee049d6c7664c4b66ab349c07828737a6d4`。这是本次临时配置的证据，不是所有个性化构建的固定摘要。

## 逐型号补测

[完整补测 40620075046](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40620075046) 已逐一检查 863 个公开非 x86 档案：841 个默认组合通过，22 个未通过。每个成功型号均实际编译、检查软件清单并校验输出文件；工作流绿色本身不代表每个型号均通过。完整逐文件证据保存在 `updates/profile-coverage.json`，失败型号与已测试替代路径另见 [机器可读清单](release14-profile-failures.json)。

R3D 默认配置的错误包名仍单独记录为失败。[修正组合 40622541784](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40622541784) 已在同一平台资源指纹下实际编译成功，保留四个温度/风扇组件。网页只在证据指纹完全匹配时提供显式应用按钮，不静默删除驱动，不将原始失败记录改成成功。

其余 21 个默认失败都在 rockchip/armv8 平台。实际依赖预检指出缺少 PCAT、Broadcom 固件、AIC8800、YT921x、ADC 按键或 RFKILL 等包；没有通过删除这些组件来凑成功数量。[只读 SDK 诊断 40630422550](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40630422550) 核对作者原 SDK 的 SHA256、1,598 个内置 IPK 控制信息、1,738 个虚拟提供名和内核配置。计入内置软件及虚拟依赖后，仍缺实际默认包的 21 个型号集合与实际编译失败完全一致。单纯的索引名称缺失不能当作编译失败；失败数量只取实际编译报告。驱动、固件和对应 ABI 仍需完整匹配，不混装其他发行版的内核包。

[官方替代实际编译 40629530849](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40629530849) 的五组均成功：Radxa ROCK 3C、ROCK 4D、ROCK 5 ITX/ITX+、ROCK 5C/5C Lite、ZERO 3W；另补齐 [Linkease EasePi R1 实际编译 40631194572](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40631194572)。六组均使用现有网页可选的官方 25.12.6、相同设备 ID，完成依赖、真实完整 sysupgrade 镜像及文件校验。已核对当前网页目录，余下 15 个缺包型号没有同 ID 的官方 25.12.6 选项。使用替代时选择官方版本并搜索相应型号；Kwrt 失败仍保留，官方源不包含的第三方插件不会被冒充为可选。此结果不等于六台实体设备已启动。

## 四个盒子资源的补查

当前已批准的 242 个型号、8 个固定内核和 10 组实际打包/回读证据继续保留。本轮核对公开最新资源：型号库及打包脚本未变，八个内核的资产编号、大小和 SHA256 也未变；辅助仓库发生变化仍需要重新打包验收，不能仅凭主文件相同就批准。

[新资源实际打包 40628941641](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40628941641) 已完成全部十组：覆盖八个内核及 Amlogic、Rockchip、Allwinner，实际编译 ROOTFS、生成 Btrfs 镜像，再只读检查 DTB 摘要、引导配置、内核模块版本与个人设置。全部通过，汇总前再次读取公开资源固定值一致；候选为 `box-20261028-cbb1e358`、242 个资源匹配型号。此公开临时测试仅保存报告，没有读取私有输入或写入私有批准目录；网页继续使用此前正式批准版本，不能把十组代表检查说成 242 台实机测试。

另下载并校验了 rk35xx 5.10.160、rk35xx 5.10.160 flippy-2412a、stable 6.12.111 和 stable 6.18.55 四份原作者资产，只读检查其中与各型号允许系列对应的准确 DTB，仍未找到匹配文件：

| 型号 | 必需 DTB | 上游限定 |
|---|---|---|
| kickpi-k11c-v12 | rk3566-kickpi-k11c-v12.dtb | rk35xx/all |
| smart-am40 | rk3399-smart-am40.dtb | stable/6.12.y |
| station-m1 | rk3328-box-trn9.dtb | stable/6.18.y |
| rk3318-box | rk3318-box.dtb | stable/6.18.y |

这些条目继续排除。没有替换相似型号的 DTB、放宽内核限定或将资源检查冒充实际开机。

## 尚受外部条件影响

私有仓库仍被 GitHub 拒绝启动 runner，已观察到的提示为账户付款或消费上限问题；本轮最新私有任务 40627672081 没有 runner 和任何构建步骤。未改动计费、Secrets、令牌权限或仓库可见性。新修复已同步私有仓库，但不能把未启动的任务称为私有验收通过。Wavlink 的离线编译修复已通过公开真实断网重建，私有网页最后一次完整复验仍待该限制解除。

ESXi 尚未提供；实体开机、无线、USB/WWAN、真实代理线路继续留待对应环境。公开默认组合的覆盖也不代表全部自选包组合可以穷举验证。已完成的软件、原始证据和未完成项分别记录，旧报告与备份保留。上轮已完成范围见 [RELEASE-13.md](RELEASE-13.md)，ESXi 接手项见 [ESXI-ACCEPTANCE.md](ESXI-ACCEPTANCE.md)。

本轮汇总见 [机器可读验收记录](release14-verification.json)。源码、网页快照和 Git 历史另作新增备份，附 SHA256；不覆盖上轮备份。
