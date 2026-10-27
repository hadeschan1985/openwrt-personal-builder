# 玩客云与电视盒子云端交付验证

日期：2026-10-27。网页版本：20261027-4。全平台最终回归仍在进行，完成后本报告将补入批准版本及证据。

## 已通过的实际测试

- [玩客云完整构建 40496482362](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40496482362)：正确作者 ImageBuilder 保持原始公布的 SHA256，依赖解析、实际烧录包生成、Amlogic CRC、boot/rootfs 两个分区逐字节回读通过。[来源与修复](ONECLOUD-COMPATIBILITY.md)。
- [盒子四组合 40498698494](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40498698494)：四组全部真实构建、打包与成品只读回读通过。DTB 摘要/compatible、全部可读原生模块的 vermagic、个人首次开机脚本摘要均核对；没有刷机或启动实体设备。
- [完整代码检查 40499546719](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40499546719)：JavaScript 75 项、Python 127 项，云端合计 202 项通过，没有跳过。Windows 本地检查中两项 Linux 工具检查跳过，云端补齐。

| 盒子型号 | 固定内核 | 核对模块数量 | 结果 |
|---|---|---:|---|
| Phicomm N1 / s905d | 6.6.160-ophub | 2668 | 通过 |
| HK1 Box / Vontar X3 | 6.12.114-ophub | 2897 | 通过 |
| OrangePi Zero3 / Allwinner | 6.18.58-ophub | 3159 | 通过 |
| Orange Pi 5 Plus / Rockchip | 6.18.58-ophub | 3159 | 通过 |

三个内核和 209 个型号的实际 DTB 资源已通过独立核验。209 是资源匹配档案，不是 209 组实际构建或 209 台实机验收；不能与主目录的 865 档案直接相加。[盒子范围与流程](BOX-COMPATIBILITY.md)。

## 本轮修复

找回作者正确的玩客云构建器，校验整个 GitHub 产物及其中唯一文件，并在私有仓库保留可追溯缓存。没有改写原先的期望摘要，没有删除旧产物。

替换作者服务器专用的玩客云和 ARM64 盒子打包钩子。玩客云现在生成真实 USB-burn 容器，原生中间磁盘不作为烧录包交付。盒子改用固定公开打包源码及配套内核/模块。

原盒子打包器会在主机上 source 固件发行文件，本项目移除此行为；用户初始化内容只复制到设备镜像。最终回读使用只读 loop 和禁止日志回放的当前内核参数，校验失败保持失败，不用忽略错误绕过。

网页新增型号、内核、自动 DTB、模板保存与恢复、导出配置，以及混装原生内核驱动的拦截。ROOTFS 中间输入与最终 Btrfs 镜像明确区分；下载仍按单个固件文件提供，增加盒子磁盘和 EMMC 烧录包的格式说明。

## 最终回归

[全部非 x86 平台回归 40499546656](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40499546656) 已启动，包含恢复后的玩客云和原有平台。运行中保持此前已批准版本；只有全部要求的代表构建通过、上游未漂移且来源身份匹配时才批准新目录。

## 边界

尚无实体设备或 ESXi 环境，未刷机、写个人电脑物理盘或改动家庭网络。实体启动、无线、USB/WWAN、真实代理线路与 ESXi 宿主机仍未验证。盒子新内核不会自动从 ophub 提升，当前只开放明确固定的三版；完整软件源长期快照也不在本轮范围。
