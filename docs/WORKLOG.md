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

- 两个远端仓库已创建并接入；Pages 未发布，真实 Actions 构建未运行，固件与硬件启动均未验证。
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
