# 个人固件工作台交付说明

网站已经上线，无需 VPS，不含会员或收费系统。

- 网站：https://hadeschan1985.github.io/openwrt-personal-builder/?v=20261025-6
- 私有构建与下载：https://github.com/hadeschan1985/openwrt-personal-builds/actions/workflows/build.yml
- 本机完整项目：E:\OpenWrt-Personal-Builder

## 日常使用

1. 打开网站，选择设备与版本。需要 PassWall/OpenClash/NAS 等组件时选择 Kwrt x86/64。
2. 按需要选择软件与系统设置，查看右侧检查提示。
3. 当前已连接的网页可以直接点“构建新固件”；记录自动显示中文进度。完成后展开任务，下载 ZIP 并使用页面的本机校验。
4. 关闭或刷新网页会清除内存里的授权。重新连接需在网页输入自己的短期令牌；也可使用“复制构建配置 → 打开 GitHub 开始构建”的免令牌方式。

网页专用令牌仅授权私有构建仓库，2026-11-24 到期，不在源码、配置或本机交付文件中。GitHub 的一次性令牌显示页面已保留，令牌不要发到聊天或任何第三方网站。

## 首次实际使用前

构建真实联网固件前，请在私有构建仓库 Settings → Secrets and variables → Actions 中自行设置 ROUTER_PASSWORD，并勾选网页“设置后台密码”。拨号或无线密码按需设置；无需把密码告诉助手。默认无密码配置仅供流程实验。

本项目不会自动刷机或改动家庭网络。必须确认具体设备、网口、引导方式与恢复方式再写入硬件。现有测试产物都标注用途，不是替你选定设备的生产固件。

## 已完成的验收

网页实际连接私有仓库、上传文件、直接提交构建、读取状态、下载与 SHA256 校验已通过。初始 13 次隔离虚拟机验收后，又完成 9 组软件组合（25 种明确指定软件）及 6 次引导回归，前一轮新增 15 次开机验证；这些包含重复基线，并非逐台实体设备验收。当前 63 项云端代码/配置检查通过。历史证据见 TESTING.md、PACKAGE-TESTING.md、verification.json、software-qa-verification.json、web-e2e-verification.json；本次进一步完善见 RELEASE-6.md。

Kwrt 当前自订构建仅 x86/64；官方目录不是本项目逐台实测清单。电视盒/任意内核/DTB/EMMC 未接入；实体 USB/WWAN、实际代理订阅和 ESXi 宿主机未测。不能承诺所有可选包任意组合均可用。

成功产物当前保留 7 天，失败日志产物 3 天；需要的固件请及时下载。私有 Actions 使用账号实际配额，未启用付费 runner 或自动充值。

功能研究与自建模块、复用能力、版本建议及风险见 FEATURE-MAP.md；详细操作见 USAGE.md；工作过程见 WORKLOG.md。

## 本次易用性完善

新增五组完整软件组合、实际依赖预检、中文自动进度、请求编号防重复提交、下载包 SHA256 本机校验和到期提示。未增加任何账户权限、VPS、收费系统或外部服务。Sites 技能只用于本地页面准备与响应式验收，生产托管仍是 GitHub Pages + Actions。

本版新增及既有代码检查合计 63 项（Python 38、JavaScript 25；Windows 缺 7-Zip 时跳过一项，Linux 完整执行）。本版真实回归和网页验收详情见 RELEASE-6.md。
