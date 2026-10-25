# 工作记录

## 2026-10-25

- 用户选择 GitHub Pages + GitHub Actions，个人自用，不实现会员/付费。
- 用户授权在 E 盘根目录建立文件夹保存工作。
- 已确认 E 盘可用，项目目录 `E:\OpenWrt-Personal-Builder`。
- GitHub 连接识别账号 `hadeschan1985`；当前可访问仓库列表为空。
- 当前连接提供仓库文件读写等功能，未提供新建仓库或启用 Pages 的专用接口。先完成可审查的本地项目，再处理远端接入。
- 核对官方版本列表：当前 stable 为 25.12.6，oldstable 为 24.10.8。构建时使用明确版本和目标，不使用不固定的 latest 包组合。
- 初始交付以真实设备元数据、配置校验、首次启动配置、Actions 构建和产物为中心；任何未接通的 Kwrt 专属能力须在界面明确标识，不伪装为已支持。

### 本地基础版已完成

- 自有静态 HTML/CSS/JavaScript 页面；设备搜索、软件选择、系统/网络设置、输出设置、非敏感模板与配置导入导出。
- 同步 25.12.6 / 24.10.8 共 3659 个版本/设备配置条目；默认版本 1941 个设备档案。x86/64 分别有 11199 / 10379 个包名元数据。
- GitHub REST 集成：连接仓库、当前会话令牌、工作流触发、运行记录、私有仓库文件包上传。未向实际仓库提交任何请求。
- Actions 工作流：代码检查、公开前端 Pages 部署、ImageBuilder 云构建；action 引用固定到已核对的 commit。
- Python runner：输入校验、官方 ImageBuilder SHA256 检查、套件/文件配置、受限解包、输出筛选、VMDK 后处理、清单核对与 SHA256。
- 7 个 JavaScript 测试、14 个 Python 测试通过；3 个工作流 YAML 解析通过。
- 浏览器检查：默认设备载入、DDNS 快捷按钮同步、旁路由配置导出、NanoPi R4S 跨架构资料载入通过；浏览器无 error/warn。
- 预览截图保存在 work/preview.jpg；本地 HTTP 预览仅用于检查，不代表已经上线。

### 尚未完成 / 下一步

- 两个远端仓库已创建并接入，Pages 已发布，首次真实 x86/64 Actions 构建成功；固件尚未进行开机或硬件验证。
- Kwrt 专属 feed/builder、电视盒/内核/DTB/EMMC、7Z、包内 IPK/APK 安装尚未接入，界面和构建器明确标识限制。
- 采用公开网页仓库 openwrt-personal-builder，以及私有构建仓库 openwrt-personal-builds；不需要用户再次创建仓库。

### 仓库创建与权限接入进展

- 用户进一步授权：由助手创建空白仓库并设置权限。
- 已使用 Chrome 中现有 GitHub 登录会话创建：
  - https://github.com/hadeschan1985/openwrt-personal-builder （公开）
  - https://github.com/hadeschan1985/openwrt-personal-builds （私有）
- 两个仓库均从空白开始，未勾选 README / .gitignore / license。
- 连接可识别用户身份并读取公开仓库信息，但写入 README 的请求返回 403 Resource not accessible by integration，未成功提交任何远端文件。
- GitHub 应用安装列表未发现 ChatGPT 仓库授权；安装与账号查询工具也返回空列表。已安装的 GitHub 插件本身处于启用状态。
- 浏览器已停在 https://github.com/settings/apps/authorizations 的 Confirm access 页面，GitHub 要求本人重新输入密码。已向用户请求在页面自行验证，未读取或输入任何密码。
- WSL 当前未配置 Linux 发行版；不安装额外系统环境，真实固件构建仍计划在 Actions 执行。
- 额外核对：默认配置要求的软件包均出现在当前 x86/64 包索引中。
- 已下载并核对校验值的 actionlint 1.7.12 对三个工作流检查通过。
- 已生成本地源码快照 work/source-snapshot.zip，便于中断后恢复。

### 内部浏览器接续与授权完成

- 用户完成 GitHub 身份复核后，Chrome 控制连接持续超时；用户要求后续全部使用 GPT 内部浏览器，已遵从。
- 内部浏览器确认 GitHub 已登录，并明确显示 Codex Connector 已获账号身份授权、但未安装到任何账号。这是仓库查询为空和写入 403 的原因。
- 用户在实际安装前确认“仅这两个仓库”，已完成安装；GitHub 返回 installation 174920950，repository_selection 为 selected。仓库查询现在只返回两个项目仓库，私有仓库读取成功。
- 补充安全校验：Wi-Fi SSID 必须与密码 Secret 同时使用；网页提前校验旁路由子网、网口与输出组合。
- 补充文件包清除功能，切换设备时不沿用旧的待上传文件；文件扩展名大小写统一。
- 当前自动测试：11 项 JavaScript、15 项 Python 通过，三个工作流 actionlint 通过。
- 内部浏览器复查：无密码热点被阻止，启用密码引用后通过；文件包路径可清除，未删除任何仓库文件。
- 接下来上传源码并实际运行 Pages 与默认 x86/64 构建；完成前不标记已上线或构建成功。

### 首次部署与构建实测

- 两个仓库完整源码上传成功，树 SHA 8052daadc7e3b6587da87bdd38d8ab976da655ac 与本地提交内容完全一致。
- 两个仓库的代码/配置检查均在 GitHub 成功执行；私有仓库的 Pages 工作流按规则跳过。
- 首次网页发布因仓库尚未启用 Pages 而失败。通过内部浏览器将 Source 设置为 GitHub Actions 后，重跑成功；未变更付费套餐或自定义域名。
- 网页地址：https://hadeschan1985.github.io/openwrt-personal-builder/ 。部署记录：https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40127485218 （attempt 2 成功）。
- 线上检查：设备/软件索引载入，DDNS 点选与导出、无令牌手动构建入口、Wi-Fi 安全提示均通过；浏览器无 error/warn。
- 首次真实构建：https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40127788108 ，成功，用时 3m 15s。
- 产物 firmware-1（25,017,842 bytes），GitHub archive SHA256 d827458bc4a5b90871ce56a981d6265f900924cdf246d835459d48f8ff51fb7c；已下载并核对一致。
- 离线检查通过：包内所有 SHA256、产物大小、所需包清单、Gzip 完整性与磁盘分区边界；EFI 为 GPT、Legacy 为 MBR，两个映像的根分区均为要求的 256 MiB。没有挂载、启动或刷写映像。
- 扩展输出测试成功：https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40128376512 。生成两种 Ext4 磁盘、两份 streamOptimized VMDK、ROOTFS TAR.GZ、清单、日志与 SHA256。
- firmware-2（63,690,007 bytes）SHA256 f5f1dceeeae5a4b6e9352c5d7e63c06c0f3a8f850371cbe98721b5e3d697dd75；下载后核对一致，所有包内校验值、所需包清单、Gzip 完整性与 512 MiB 根分区均通过。
- 从实际 ROOTFS 内只读检查初始化脚本：可执行标记、旁路由网关、关闭 DHCP、关闭 LAN RA、openwrt-2020 主题路径和自定义 Shell 均按测试配置嵌入。未执行脚本，尚未验证启动后实际网络行为或 ESXi 兼容性。
- 本地最终检查为 11 项 JavaScript、18 项 Python 测试通过；新增离线产物校验工具 scripts/verify_artifact.py，生成校验记录供复查。

### 2026-10-25 扩展实现与真实开机验收

- 接入固定 SHA256 的 Kwrt x86/64 ImageBuilder 和独立 IPK 软件索引；官方来源继续保持版本、架构和包管理器隔离。原站可见功能、交互/API 线索、自建模块与版本建议整理在 FEATURE-MAP.md。
- 实现 NAS/iStoreX/路由狗、主页模式、主题浅深色、WWAN、iptables legacy、Lighttpd、7Z、自订 IPK 和原生 ESXi VMDK 输出。去推广外链仍保留许可和源码入口。
- 修正 Kwrt 上游不可用的出厂包名称、本地绝对软件源、被忽略的安装错误和中文拆包差异；构建器固定指纹，不静默换源或混入不匹配内核模块。
- 发现并禁用 Kwrt Makefile 在构建主机执行用户 IPK 安装脚本的路径；自订 IPK 以 payload 暂存，只在路由器首次开机安装，依赖在构建前解析，核心/内核包拒绝此路径。
- 修正首次开机 WAN/LAN 映射、HTTP/HTTPS 开关、Nginx 监听、Lighttpd CGI RPC、Argon 登录页外链注入及原生 VMDK 开关。实际包模板确认 Argon 支持 normal/light/dark 三种模式。
- 9 份云端报告、13 次隔离虚拟机开机、root 密码登录和 HTTP JSON-RPC 均通过；报告下载后逐一核对 GitHub archive SHA256。完整引导回归 40167823669、扩展矩阵 40167403974 的 5 项成功任务及 Lighttpd 修复回归 40168809787 构成最终证据。
- 测试覆盖官方/Kwrt、EFI/Legacy/VMDK、SquashFS/Ext4、旁路由、三种 Web 服务器、Docker、USB/蜂窝包和设备端 IPK。未刷实体设备，不等于 USB/WWAN 实物、实际代理订阅或 ESXi 宿主机全部验证。
- 现有 29 项 Python 与 14 项 JavaScript 检查，Windows 的一项 7-Zip 检查在 Linux runner 完整执行。详细边界见 TESTING.md 和 verification.json。
- 网页免令牌操作简化为复制配置与打开 GitHub 两步；增加始终可用的历史入口、资料加载保护、文件/配置提交快照、超时后的防重复提交提醒和明显的无密码实验警告。
- 用户明确批准新建网页专用细粒度令牌，仅私有构建仓库、30 天、Actions/Contents 读写。GitHub 本人身份验证由用户完成；令牌不写源码、配置、文件或聊天，只用于网页会话和 GitHub API。接通和最终发布验收尚在进行中。

### 网页直接构建闭环与最终交付

- 本人验证后创建 30 天细粒度令牌，只选 openwrt-personal-builds；Actions/Contents 读写、Metadata 必需只读，没有账号级、Secrets 或工作流编辑权限。令牌内容未记录到本文件或源码，正式网页连接后输入框已清空。
- 浏览器联调发现将原生 fetch 作为实例方法调用会导致 Illegal invocation；改成包装函数，补充默认 fetch 接收者回归测试。JS 现为 15 项，加 Python 29 项共 44 项云端检查；本地 Windows 跳过一项 7-Zip，云端完整执行。
- 为避免 GitHub Pages 缓存旧模块，发布脚本/样式使用版本标记。新版部署 40170856198 成功，public commit c0ba25f87e76ff42f36b6c6c4598be71726303c0。390 像素移动布局、模板可见性、WAN eth0 自动匹配 LAN eth1、资料恢复与免令牌两步流程已检查。
- 已由正式网页完成私有历史读取、文件包上传和构建提交；任务 40170974151 成功，产物 firmware-3。无敏感测试 ZIP 只保留在私有仓库，未同步公开仓库。
- 下载后核对 GitHub archive SHA256 2900ec86e32d24ca44e49142177bd5f44fe05468386d6057d51aa2df1bca2d7a；包内校验值、Gzip、磁盘分区、256 MiB 根分区和软件清单通过。ROOTFS 只读确认测试覆盖文件、主机名和签名真实生效于输出文件。
- 原站功能/架构/自建拆解/复用边界/版本建议/风险见 FEATURE-MAP.md；使用方法见 USAGE.md；验收与未测边界见 TESTING.md 和 verification.json。未对真实设备刷机或更改现有家庭网络，也未触发付费。
- 本机直连 GitHub Git 传输失败，但连接器提交成功；本地源码树与上传树一致，另提供源码 ZIP 和 Git bundle。不能将该网络问题误记为构建失败。

### 继续进行多软件组合与边界调试

- 用户要求继续添加各种定制软件测试，并给出后续改善建议。增加固定 9 组配置，覆盖 25 种明确指定的软件/协议/代理包，组合任务最大并行 2，运行仅限隔离虚拟机，不启用付费资源、不刷实体设备。
- 软件组合回归 40175491386 的 9 个任务全部成功：官方网络/存储，Kwrt DNS、PassWall2、OpenClash、HomeProxy、HomeProxy Pro、Nikki、小插件。移除 PPP/PPPoE、nano/htop 后在实际包数据库确认不存在；交叉验收 Ext4、Bootstrap 深色、OpenWrt 2020、Argon 浅/深色。
- 测试框架修改后，基线回归 40175491357 两个来源均成功，完成 EFI/Legacy/VMDK 六次启动。本轮合计 15 次开机，11 份报告下载后逐一核对 GitHub archive SHA256；原始报告摘要保存在 software-qa-verification.json。
- 集成回归版本 b46e1b3570cfb5ae5d71473b338b47caab900677；后续输入防护只改变非法输入的提前拒绝与网页操作，不改变通过配置的输出选择。最终代码检查 40176507735 明确显示 Python 34、JS 17，均完整通过。
- 发现自订软件框绕过 nft 约束、HomeProxy Pro 漏列、主题/代理同时添加移除及禁用按钮导致已选冲突项不能取消；修复前后端检查，统一前端 NFT_ONLY 清单，浏览器实测错误拦截、取消后恢复和防止重新新增均通过。
- 本地界面验收后发布前端资源版本 20261025-5；Pages 部署 40176503093 成功，内部浏览器确认正式网页载入带该版本标记的资源和真实设备目录。旧已连接网页没有强制刷新，避免无提示清除当前令牌会话。
- 源码与报告文件扫描未发现实际 GitHub PAT 字符串。私人令牌仍不进入源码、配置、日志或交付文件。
- 包安装与后台基本集成不等于核心/订阅/外网服务或实体硬件全部可用；改善优先级和未测范围明确列于 PACKAGE-TESTING.md。没有新增任何用户账号权限或收费服务。
