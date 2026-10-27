# 功能地图与自建架构

观察日期：2026-10-25。原站界面、公开脚本、下载目录与实际构建验证分开记录；“可选包”不等于每一个插件及硬件组合都已实测。

本项目实现状态更新至 2026-10-27；具体结果以 [RELEASE-11.md](RELEASE-11.md) 为准。

## 1. 原站可见功能地图

| 区域 | 原站可见行为 | 本项目对应实现 |
|---|---|---|
| 首页/设备 | 搜索型号，按平台/版本读取设备档案；观察时登录页面显示 1119 台 | 官方目录独立保留；Kwrt 与公开目录匹配 865 档案、24 平台，新增多型号自动验收版本 |
| 设备详情 | 型号、平台、内核、生成日期、默认后台与历史版本 | 设备卡片、源/架构/内核、上游预编译文件及 SHA256；自己的构建历史在 GitHub |
| 出厂包移除 | 点击包名表示从默认包中删除 | 读取 default_packages/device_packages，保护核心包，构建后检查实际清单 |
| 常用包/自订包 | 快捷按钮、空格分隔包名、可用包数 | 同类交互；按所选构建源真实索引开放，支持包名搜索 |
| 防火墙 | 用 iptables 替换 firewall4；禁用部分 nft-only 插件 | 依赖转换、冲突校验、实际输出清单核对 |
| 代理 | PassWall、PassWall2、HomeProxy/Pro、SSR-Plus、OpenClash、Nikki、Momo、Meow、FullCombo、Clashoo、Honk、luci-xray、Open-Box、Daed、HiJpass、v2rayA | Kwrt 索引中按对应 luci-app-* 选择；官方源缺失的包不会伪装可用 |
| 后台 IP/密码 | IPv4 与 root 密码输入 | IP 写入首次开机配置；按使用者要求临时 root/root，也可引用私有仓库 Secret |
| 主题 | 多主题、默认主题、Argon/Bootstrap 深浅色等 | 多主题与默认项；共享包的深浅色用路径或 UCI 配置切换 |
| Docker | 安装管理组件及依赖 | luci-app-dockerman 及构建源依赖；数据盘配置仍依硬件情况 |
| 假装 iStoreOS/路由狗 | 对应增强后台/NAS 界面 | Kwrt 的 luci-app-istorex、luci-app-routerdog 与主页设置 |
| 默认主题模式 | 原站选项为自动、概览、面板，不是简单的深/浅色开关 | Kwrt 主页模式，另提供 NAS/iStoreX/路由狗模式及依赖检查 |
| USB 网卡 | 有线/无线驱动组；无线在原站受赞助限制 | 无会员限制的兼容驱动组；具体芯片仍需实际硬件验证 |
| Web/HTTPS | Nginx、Uhttpd、Lighttpd，HTTPS 偏好 | Uhttpd、Nginx；Lighttpd 使用 Kwrt 集成包。证书在设备生成，不复用上游私钥 |
| IPv6/旁路由/DHCP | LAN 通告、网关和 DHCP 条件显示；旁路由隐藏拨号 | 同类条件交互、子网检查、首次开机 UCI 配置 |
| EFI/Legacy | 按设备选择启动格式 | x86 输出筛选并核对实际文件；不把下载成功当成开机成功 |
| WWAN | 原站当前是 wwand/eSIM/MBIM/MHI/NCM 组合 | Kwrt 使用同类 wwand 组件；官方环境使用 ModemManager。实际蜂窝模块/运营商仍需实物与账户验证 |
| WAN/交换网口 | x86 eth0 WAN/交换默认端口；按设备条件显示 | 明确的 WAN、LAN eth 端口设置；缺失 WAN 配置时先创建接口 |
| PPPoE/Wi-Fi | 账号、密码、SSID | 私有 Secret 引用；SSID 不能在没有密码时生成开放热点 |
| 主机名/Overlay | 自定义名称与根分区容量，受设备限制 | 名称检查、x86 64–6144 MiB；固定 Flash 不开放任意扩容 |
| 签名/去外链 | 发行信息与推广链接调整，原站受赞助限制 | 自订启动横幅；隐藏推广链接并保留许可、文字和源码入口 |
| 文件系统 | SquashFS/Ext4 | 按构建器能力构建并筛选；不靠改扩展名转换 |
| VMDK/ROOTFS | ESXi 磁盘、Docker/LXC 根文件系统 | 官方 streamOptimized VMDK、Kwrt 原生 descriptor+flat VMDK ZIP、ROOTFS TAR.GZ；ESXi 实机另测 |
| 初始化 Shell | 嵌入首次开机脚本 | 写入 uci-defaults，仅在路由器内运行，需要私有仓库 |
| 文件包/IPK | 文件覆盖、包内 IPK 安装、上传历史 | ZIP/TAR.GZ/TGZ/7Z 受限解包；IPK 在设备首次开机安装。GitHub 保存文件版本，不复制原站会员上传系统 |
| 自动填写 | 浏览器保存表单 | 非敏感配置自动填写、命名模板、JSON 导入导出；不保存访问令牌和初始化脚本 |
| 构建/日志 | 排队、构建中、错误、完成、stdout/stderr | GitHub Actions 的真实状态/日志，不显示演示任务 |
| 下载/历史 | 文件格式说明、SHA256、历史版本 | Artifacts、清单、SHA256SUMS、任务记录；保留期不是永久 |
| 登录/赞助 | WordPress/UsersWP 登录、赞助身份与 VIP 队列/字段限制 | 不实现会员；仅使用 GitHub 自身的私有仓库权限保护自己的内容 |
| 特殊设备 | 电视盒、内核/DTB、EMMC 等条件选项 | 按设备档案提供 SD/EMMC/sysupgrade，N1 新版已修复；玩客云因校验问题暂停。任意内核和 DTB 切换仍不提供 |

## 2. 使用流程

选择构建源和设备 → 选择/移除软件 → 配置系统与输出 → 校验 → 提交私有 Actions → 查看日志 → 下载 Artifacts → 校验 SHA256 → 使用经过验证的方式安装。

网页直接提交需要单独的最小权限 GitHub 授权。ChatGPT 的 GitHub 连接不能自动变成公开 Pages 网页的授权。免令牌路径是复制配置后在 GitHub 的 Run workflow 粘贴；这不需要 VPS。

自订文件在启动构建时才上传，包含个人设置的固件不公开发布。项目不自动刷写实体设备。

## 3. 原站技术线索与推测

公开 DOM 资源包含 WordPress、UsersWP、jQuery、Bootstrap、FormStorage；可据此判断登录与网页外壳用了这些组件。

公开 index.js 显示 ASU 风格的 `/api/v1/build`：OPTIONS 检查、POST 提交，带一次性验证头。客户端处理 200 完成、202 排队/构建中，以及 400、422、500 错误；约 5 秒轮询。返回结构包含 request_hash、stdout/stderr、queue_position、imagebuilder_status，完成后指向 `/store/{request_hash}`。

设备与包索引使用 `/json/v1/overview.json`、按版本/目标的 index.json 和架构索引。上传辅助脚本使用 WordPress AJAX 与 nonce；浏览器自动填写使用 localStorage。

这些是公开客户端代码线索，不是本次抓取的私有后台流量；没有调用原站构建 POST、绕过验证头、触发赞助或尝试后台管理。不能由此认定其服务端就是未经修改的官方 ASU。

## 4. 自建模块拆解

```text
GitHub Pages 表单
  → 本机浏览器校验/模板
  → 授权后的 GitHub API（或 GitHub 手动提交）
  → 私有仓库 Actions
  → 校验输入/选择固定 ImageBuilder/准备包与文件
  → 官方或 Kwrt ImageBuilder
  → 清单/输出格式/SHA256 检查
  → 私有 Artifacts + Actions 日志与历史
```

无需常驻 Python 服务、Redis、SQL 数据库或 VPS。GitHub 负责作业、日志、权限和限期储存；本项目负责配置转换、安全边界、适配与验收。

代码分工：`site/` 表单与 GitHub 请求；`scripts/catalog.py` 目录；`scripts/build.py` 验证与构建；`configs/builders.json` Kwrt 固定校验值；`scripts/smoke.py` 隔离开机回归；`verify_artifact.py` 下载校验。

## 5. 可复用与需自建

| 直接复用的公开能力 | 需要自行开发或维护 |
|---|---|
| OpenWrt ImageBuilder、profiles、包索引、原生映像格式 | 表单、模板、字段到包/UCI 的转换、兼容性规则 |
| ASU 的公开协议/目录设计 | 本项目不用常驻 ASU，改成 Actions 批处理入口与状态适配 |
| Kwrt 公开构建器、插件和主题包 | 校验值固定、服务器本地路径修正、失效默认包处理、设备端 IPK 安装边界 |
| qemu-img、QEMU、SHA256 工具 | 输出选择、验证报告、隔离策略、回归矩阵 |
| GitHub Pages/Actions/Artifacts/私有仓库 | 个人使用流程、最小授权、失败提示、保留期说明 |

原站 Logo、会员系统、未公开后端和私有数据库不复用。各上游包保留各自许可证。

## 6. 版本建议

- MVP：x86/64、官方固定版本、设备/包选择、系统网络设置、EFI/Legacy、日志/下载/校验、模板。已完成基础构建和开机验证。
- 个人增强版：Kwrt、代理、主题、NAS、7Z/IPK、VMDK/ROOTFS、防火墙/Web 服务器组合。以 TESTING.md 的实际结果为准，不把进行中项目计入通过。
- 多型号版：Kwrt 全公开目录、各平台固定构建器、逐文件下载、每日检测和代表型号编译后自动批准。当前 22 个非 x86 平台通过，玩客云继续因上游校验问题暂停。
- 后续：实体 USB/WWAN/ESXi、任意内核/DTB、玩客云上游资源修复、完整软件源快照。需要对应资源与独立验证。

## 7. 风险与难点

核心难点是构建环境与包的内核 ABI/依赖一致性，而不是表单外观。Kwrt 官方/第三方源滚动更新，固定构建器也不代表所有包永久可复现。发布方 SHA256 只验证下载一致性，不等于完成源码安全审计。

GitHub 配额、构建时限和产物到期要遵守账号实际限制；没有启用付费 runner 或自动充值。公开 Pages 不能安全内置私人令牌。自订脚本/IPK 拥有设备 root 权限，上传者必须信任其内容。

错误的网口映射、DHCP/网关、Flash 分区、引导格式可能导致失联或刷机失败。虚拟机回归能减少软件问题，但不能替代具体设备的恢复方案与实体测试。

参考：[原站](https://openwrt.ai/)、[公开客户端](https://openwrt.ai/index.js)、[Kwrt](https://github.com/kiddin9/Kwrt)、[OpenWrt ASU](https://github.com/openwrt/asu)、[GitHub Artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)。
