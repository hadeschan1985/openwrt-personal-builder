# 交钥匙完善版 · 20261025-6

本次范围是把现有个人工作台变得更易用、更容易排错，不增加 VPS、会员或收费服务。源码与工作过程在 E:\OpenWrt-Personal-Builder。

## 已实现

| 功能 | 行为与边界 |
|---|---|
| 五组软件组合 | 官方网络、官方存储、Kwrt PassWall2 双核心、HomeProxy 与常用工具；增量添加，不覆盖私人设置 |
| 真实依赖预检 | 使用对应 ImageBuilder 的 make manifest 解析；缺包/冲突/移除包被依赖恢复时在生成映像前停止；不会运行用户 IPK 脚本 |
| 中文实时状态 | 自动刷新任务与步骤，后台暂停，回来继续；失败按阶段提示并保留完整 GitHub 日志入口 |
| 请求防重复 | 唯一请求号匹配真实任务；超时不自动重提；刷新后可恢复请求号，但令牌仍只留在内存 |
| 下载与本机校验 | 显示私有产物大小、到期时间、GitHub ZIP SHA256；文件仅本机计算，不上传；区分 ZIP 和映像校验 |
| 基础追溯 | 输出构建器 SHA256、依赖预检结果、代码版本及配置指纹；不宣称滚动软件源已完全可复现 |

## 当前验收记录

- 63 项代码/配置测试通过云端检查，Windows 本地 62 项通过、一项 7-Zip 环境检查跳过。
- 正式 Pages 部署 40192746820 成功，源版本 1069e39a5e3c93d70f96d616fc3885415df37b79。
- 内部浏览器实际使用新版读取私有任务，显示中文步骤、产物到期时间与 SHA256。
- 已有真实 firmware-3 ZIP 在网页校验通过；换成错误 ZIP 时明确拒绝；刷新后仍保留本标签页的校验结果。
- 手机宽度 390（可用内容宽 375）下无横向溢出，五组模板均可见。
- 新版网页已实际提交测试请求 056216fc-6fe5-4f16-8682-a5f89adb2fbb，按钮立即禁止重复提交；[任务 40193155017](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40193155017) 成功后，页面自动识别完成并恢复按钮。
- 该任务解析出 227 个包后生成 Legacy 映像，产物 firmware-4 的 ZIP SHA256 为 `38874b1d24d8e44a7907933e0d1f375b965e48a38086ef9edf371c34d380e595`。下载到本机后，ZIP 与包内文件校验、MBR 分区、256 MiB 根分区、请求软件清单均通过；新版页面对这份 ZIP 的本机校验亦通过。此单独网页产物没有额外开机，代表组合的开机测试属于下述隔离回归。
- 本轮正式页面测试结束后已恢复空白日常默认配置，避免 QA 主机名、签名或测试网络地址留在自动填写中。授权仍连接在新版页面内存中。
- 另检查 NanoPi R4S 搜索、详情和包索引，实际载入 11,113 个可用包；x86 专属选项正确禁用。仅为页面资料验收，没有对 ARM 实机刷机或开机。
- [九组真实回归与缺包负向检查](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40192493869) 已全部成功：9/9 组实际构建、BIOS 开机、设备内安装/移除清单、随机密码认证、HTTPS LuCI 与 RPC 检查通过，另有缺包负向检查确认未生成映像。PassWall2 组合这次明确包含 Xray、sing-box 与证书包，HomeProxy 明确包含 sing-box。
- 本轮新增 9 次隔离开机，不把未另行开机的网页产物计入。10 份报告全部下载到本机并逐份核对 GitHub ZIP SHA256，机器可读汇总为 release6-verification.json。
- 代码检查 40193188058 日志明确显示 JavaScript 25/25、Python 38/38，Linux 无跳过；本地 Windows 仅 7-Zip 环境检查跳过一项。

## 不包含的承诺

包安装/后台登录检查不等于代理节点、DNS 业务、共享读写或实体硬件已全部验证。平台不自动刷机、不修改家庭网络。个人版仍受 GitHub 实际配额、令牌期限、上游软件源可用性和产物保留期限约束。测试固件为 QA ONLY，不作为生产刷机固件交付。

技术依据：[OpenWrt ImageBuilder Makefile](https://github.com/openwrt/openwrt/blob/openwrt-25.12/target/imagebuilder/files/Makefile)；[GitHub 产物 API](https://docs.github.com/en/rest/actions/artifacts)。API SHA256 对应 ZIP，而不是解压后的单个固件。
