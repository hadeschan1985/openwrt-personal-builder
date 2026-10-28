# 玩客云公开构建环境与烧录包修复

本轮解决的是云端可构建、可独立下载和文件格式验证。没有玩客云实体设备，没有刷机或声称设备已开机。

## 正确构建器来源

原 CDN 下载得到的文件与发布方公布的 SHA256 不同，因此此前正确停止构建。没有通过改写期望校验值绕过此问题。

在 [Kwrt 作者原始运行 38270404059](https://github.com/kiddin9/Kwrt/actions/runs/38270404059) 的 `10.12_amlogic_meson8b` 公开产物中找回正确版本：

- 作者源码提交：`72d10a7d43d85dae0ab057493d5a4aa81e97ac82`。
- 作者产物 ID：`11760922364`，ZIP 613745374 字节，SHA256 `45c39e568391b77cb628086e5f8f3eb96374e323ecef959ffc9d731e5237c57d`。
- 整个 ZIP 通过 GitHub 提供的摘要校验后，只读取其中唯一的 ImageBuilder 文件，校验 ZIP 成员 CRC、文件大小及原先公布的 SHA256。
- 正确 ImageBuilder 313895435 字节，SHA256 `e29abe52fea3bdaf77a0af313ccb5c6f06c6564a4f7cdb27d41fd9215d6926b5`，与原站公布值完全一致。
- 公共下载使用 nightly.link 作为 GitHub 产物重定向入口，字节信任依据仍是作者 GitHub 的 ZIP 摘要与原站构建器摘要。没有安装应用、输入账户凭据或放宽校验。

[来源核验 40455959521](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40455959521) 通过。[私有缓存发布 40456423339](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40456423339) 将相同字节保存在私有 Release `source-onecloud-20261012`，避免作者的临时 Actions 产物过期后无法构建。此缓存不占用网页的五个固件收藏名额，也未删除或覆盖旧版本。

缓存读取与编译分为不同步骤：仓库短期令牌只在下载步骤使用；跳转到 GitHub 文件存储时不会转发令牌。编译步骤没有仓库写权限。

## 替换服务器专用打包步骤

作者 ImageBuilder 内含 `Image/Build` 钩子，调用作者服务器 `/data/packit/openwrt-onecloud` 下未公开的脚本。普通 GitHub runner 没有该目录。即使根文件系统成功构建，原钩子也不能生成可交付的烧录包。

仅在精确识别该已知钩子后移除它，保留 LEDE 原生 eMMC 中间镜像生成。中间磁盘不能改名冒充烧录包。

后续使用 [hzyitc/AmlImg](https://github.com/hzyitc/AmlImg) 固定提交 `5ede4ed30b27c10187af5258f7e2f61f9ad71e1e` 从源码编译打包器，无额外 Go 依赖。引导模板来自 [作者固定 U-Boot 发布](https://github.com/hzyitc/u-boot/releases/tag/build-20221028-0940)，1367540 字节，SHA256 `d33d979d23b8a607447c5af424b1e24003820e7e159e540c7f47c89d45cdc491`。

按照作者 [Armbian OneCloud 的打包流程](https://github.com/hzyitc/armbian-onecloud) 把 boot/rootfs 转为 Android sparse 分区，添加 Amlogic VERIFY 项，并生成真正的 USB-burn 容器。全程只操作本轮工作目录中的普通文件，不挂载物理磁盘、不刷设备。

交付前必须重新解包容器，校验容器 CRC、全部引导组件摘要，并把 sparse boot/rootfs 转回原始分区，与构建时分区逐字节摘要和长度比对。任何一步失败均停止交付。

## 实际结果

[完整构建与回读运行 40496482362](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40496482362) 成功。依赖、实际固件、Amlogic CRC 和两个分区回读均通过。生成 `kwrt-amlogic-meson8b-thunder-onecloud-ext4-emmc_burn.img.gz`，21720246 字节。该测试产物 SHA256 为 `8c4af8da26be596015d343d7a04f3342f72974789b75902f3f559e37f42ff622`，并非所有后续个性化构建的固定摘要。

普通构建输出独立烧录文件和 `onecloud-pack-report.json`；下载仍执行本次文件 SHA256 校验。新自动验收版本需再通过全平台批准流程后出现在网页，旧固定版本的历史状态保持原样。

## 网页软件索引失效时

2026-10-28 观察到原站的 arm_cortex-a5_vfpv4 网页包索引返回 404，原来的七份 IPK 软件源索引仍完整可读。更新流程仅针对该准确目标和准确错误，改用构建器原有的原始 IPK 索引读取能力；不改构建器和软件源。全目录检查、七份索引重复摘要、实际 USB-burn 编译及两个分区回读均通过，详见 [本轮证据](RELEASE-14.md)。新的资料指纹仍需通过私有批准流程后才出现在可选更新中，旧版本不自动替换。
