# 软件组合压力测试与改善建议

测试日期：2026-10-25。范围是用户要求的“添加不同定制软件并持续调试”，不涉及实体刷机、用户订阅或付费资源。每组使用随机临时凭据，虚拟机无外网出口，不共享宿主机目录；只上传报告，不上传测试固件和密钥。

## 本轮测试设计

9 组配置覆盖 25 种明确指定的软件/协议/代理包，另加主题、NAS 和自动解析的依赖。组合测试每次最多同时执行两组，避免无界限消耗 Actions 配额。

| 组合 | 明确指定的软件与定制 | 结果 |
|---|---|---|
| 官方网络工具 | DDNS、UPnP、WireGuard、SQM、统计、网页终端；移除 PPP/PPPoE；Bootstrap 深色 | 实际构建/开机/安装及移除清单/登录/RPC 已通过 |
| 官方存储与下载 | Samba、MiniDLNA、Transmission、Aria2、硬盘休眠；Ext4；OpenWrt 2020 主题 | 实际构建/开机/安装清单/登录/RPC 已通过 |
| Kwrt DNS | SmartDNS、MosDNS、AdGuard Home、网易云音乐 | 实际构建/开机/安装清单/登录/RPC 已通过 |
| Kwrt PassWall2 | PassWall2 与 NAS/Argon | 实际构建/开机/安装清单/登录/RPC 已通过 |
| Kwrt OpenClash | OpenClash 与 Argon 浅色 | 实际构建/开机/安装清单/登录/RPC 已通过 |
| Kwrt HomeProxy | HomeProxy 与 NAS/Argon | 实际构建/开机/安装清单/登录/RPC 已通过 |
| Kwrt HomeProxy Pro | HomeProxy Pro 与 Argon 深色 | 实际构建/开机/安装清单/登录/RPC 已通过 |
| Kwrt Nikki | Nikki 与 NAS/Argon | 实际构建/开机/安装清单/登录/RPC 已通过 |
| Kwrt 小插件 | 文件管理、KMS、UU 加速、TurboACC、NAT 映射；移除 nano/htop | 实际构建/开机/安装清单/登录/RPC 已通过 |

9/9 组均成功，另有 6 次 EFI/Legacy/VMDK 基线开机成功，本轮合计 15 次开机验证。11 份报告均已下载核对 GitHub archive SHA256；机器可读证据见 `software-qa-verification.json`。

主要工作流：[组合回归 40175491386](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40175491386)。修改测试框架后另运行官方/Kwrt EFI、Legacy、VMDK 基线回归 `40175491357`。

每个成功组合要求：实际 BIOS 开机、首次开机脚本执行完毕、上传文件存在、管理 IP/网口/DHCP/主题正确、设备内包数据库有要求安装的包且没有要求移除的包、随机 root 密码认证成功、HTTPS LuCI 登录与 HTTP JSON-RPC 成功。不是只查看工作流的绿色图标。

## 本轮已发现并修复

1. 自订软件包文本框可以绕过代理插件按钮上的 nftables 规则。现在前后端均检查所有输入来源。
2. HomeProxy Pro 没包含在 nft-only 清单内，而当前实际 feed 明确依赖 firewall4；现已补齐。
3. 原检查只阻止普通包同时添加和移除，没有覆盖主题/代理。现统一检查。
4. 切到 iptables 后，已经选中的 nft-only 插件按钮会被禁用，反而无法取消。现在保留取消操作，同时阻止新增不兼容选择。
5. 新的组合验证覆盖 OpenWrt 2020 和 Argon 浅深色，修正测试框架对真实主题路径的别名映射；不把测试框架误报当作固件故障。

本轮当时的代码检查为 34 项 Python、17 项 JavaScript；Windows 本地因未安装 7-Zip 跳过 1 项，该项在 Linux runner 完整执行。浏览器实测：错误包名、文本框防火墙冲突被阻止提交，取消冲突插件后表单可恢复。后续交钥匙完善版已扩展为 38 项 Python、25 项 JS，63 项云端完整通过。

## 当时提出的改善优先级

| 优先级 | 建议 | 为什么值得做 |
|---|---|---|
| P1 | 依赖/冲突的构建前试算与易懂提示 | 当前目录主要保存包名；复杂依赖要到 ImageBuilder 才能确定。可先运行官方支持的 manifest 解析，再告诉用户“谁依赖谁”，减少昂贵失败构建。 |
| P1 | 经实测的整套软件模板与代理核心提示 | 安装 LuCI 插件不等于对应核心、订阅、策略和端口已经配置好；应明确显示缺少核心或尚未配置，而不是把菜单出现当作功能可用。 |
| P1 | 自动更新队列/阶段、中文状态、按请求编号定位任务 | 当前需要手动刷新记录，底层状态沿用英文；可改善非技术用户体验和超时后的防重复提交。 |
| P1 | 私有下载区显示清单、校验值与到期时间 | 目前真实文件和 SHA256 在 GitHub 任务页，安全但操作跳转较多；可让网页显示已授权读取到的校验信息，仍不公开固件。 |
| P2 | 软件源快照、包版本/指纹和可复现构建 | 固定 ImageBuilder 不代表滚动 feed 中每个软件永久相同；需记录完整依赖版本并规划储存上限，不能把缓存当永久备份。 |
| P2 | 只生成所选映像格式，并使用有校验的包缓存 | 本轮仅请求 Legacy 的 Kwrt 测试，底层日志仍显示生成 EFI 后再筛选。可以优化构建器开关，减少重复压缩和下载，节省时间与配额；先回归验证再启用。 |
| P2 | 插件页面/本地服务的专项功能测试 | 现有组合验证保证集成、安装与后台基本可用；下一层应测试本地 HTTP 文件管理、DNS 请求、SMB 读写、代理核心配置检查等，不依赖用户真实数据。 |
| P2 | 指定硬件与恢复流程验收 | USB/WWAN、实体网口、ESXi、固定 Flash/电视盒不能靠 x86 虚拟机替代。扩大设备支持前逐系列建立验收。 |

本轮不自动实施新的账号权限扩张、持久保存令牌、付费服务或实体刷机。所有“建议”都与已完成项目区分，不计入通过。

## 交钥匙完善版的实现进展

上述四项 P1 的基础功能已在 20261025-6 实现：同构建器实际依赖预检、五组增量模板与核心提示、中文自动跟踪与防重复提交、私有产物到期提示及 ZIP 本机校验。完整依赖树的逐层可视解释尚未实现；预检发生在云端准备好 ImageBuilder 后，不是网页瞬时离线求解。软件源快照、只生成所选格式的性能优化、本地服务业务测试与实体硬件验收仍属于后续范围，未计入已通过功能。最新回归证据和网页测试见 RELEASE-6.md。

## 验证边界

组合测试不是对全部包、全部版本、任意组合的穷举。不连用户节点/订阅，不访问外部 DNS/下载/加速服务，不把服务页面加载等同于真实线路可用。包数据库检查证明实际集成状态，不代表每个服务已按用户家庭网络配置。

测试固件使用临时凭据和专用测试标记，不能用作正式固件。报告下载后逐份核对 GitHub archive SHA256，最终结果另存机器可读汇总。

参考：[OpenWrt ImageBuilder 与 manifest](https://openwrt.org/docs/guide-user/additional-software/imagebuilder)、[OpenWrt 包管理](https://openwrt.org/docs/guide-user/additional-software/managing_packages)、[GitHub 缓存与产物区别](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)。
