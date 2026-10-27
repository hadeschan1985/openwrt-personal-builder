# GitHub 接入与部署

本项目的本地代码目录为 E:\OpenWrt-Personal-Builder。不需要切换聊天或再安装 Codex。

## 推荐的两个仓库

1. `hadeschan1985/openwrt-personal-builder`：公开网页与源码。仅发布 site/，不包含自己的文件包、密码或固件。
2. `hadeschan1985/openwrt-personal-builds`：私有构建仓库。放同一套构建脚本和 configs/，运行 build.yml，保存私人文件包与产物。

上述两个仓库已于 2026-10-25 创建。双仓库方式适用于 GitHub Free：公开 Pages 展示无敏感内容的界面，私有 Actions 保存自己的构建内容。私有仓库的 Actions 有套餐配额；不是无限免费。

GitHub 连接已识别用户。2026-10-25 经用户确认，已通过 GPT 内部浏览器安装 ChatGPT Codex Connector，仅授权这两个仓库。连接现可读取私有仓库；首次写入、Pages 发布与真实构建进度见 WORKLOG.md。不要在聊天中发送密码或访问令牌。

## 发布网页

将本项目推送至网页仓库 main 分支。进入 Settings → Pages，将 Source 设为 GitHub Actions，运行 `Deploy configuration workbench`。

工作流审计并发布源码中的完整基线快照和 site/，不在发布时读取滚动软件源。新 x86 及多型号版本由私有仓库测试批准后，在网页连接时载入。默认 github.io 域名即可，不需要另买域名。详见 UPSTREAM.md。

## 构建仓库

将代码推送至私有构建仓库 main 分支。

在 Settings → Secrets and variables → Actions 中按需设置：

- `ROUTER_PASSWORD`：路由器 root 密码。
- `PPPOE_USERNAME`、`PPPOE_PASSWORD`：拨号账号及密码。
- `WIFI_PASSWORD`：Wi-Fi 密码。

这些 Secrets 不是 GitHub 账号密码。页面通过开关引用；不会读出其值。需要相应 Secret 时，缺失会导致构建明确失败。

填写 Wi-Fi SSID 时必须同时启用 WIFI_PASSWORD；本项目不生成无密码的开放热点。固件本身会包含首次启动所需的私人配置，不能因为使用 Secrets 就将产物公开分享。

首次部署先等待私有仓库的 `Automatically follow tested upstream`（x86）及 `Automatically approve tested device updates`（多型号）完成首次批准。然后在网页选择实际设备并提交，或在 Actions 的 `Build personal firmware` 中粘贴导出配置。不要留空，否则运行仓库的官方 x86 示例配置；这与当前网页选择不同。

以后在网页配置并导出 JSON，粘贴到 config_json 即可运行。无需向网页提供访问令牌，也无需运行服务器。

## 网页一键提交（可选）

如需网页直接提交，使用只授权构建仓库的 GitHub fine-grained token：Actions 读写；上传文件包另需 Contents 读写。令牌由你在网页当前会话输入，不保存、不进入导出文件或 URL。关闭或刷新后需重新输入。

ChatGPT 已连接 GitHub 不代表 Pages 网页自动获得该连接。不要把 ChatGPT 连接凭据、GitHub token 或任何私人配置写进公开 Pages 文件。

## 自定义文件包

目前支持普通文件的 ZIP/TAR.GZ/TGZ 覆盖，最大压缩体积 12 MiB、解包体积 128 MiB，文件按固件根目录布局。网页直接提交模式仅上传到私有构建仓库 overlays/。

无令牌模式：自己通过 GitHub 上传文件包至私有仓库 overlays/，在网页填写对应路径后导出配置。

支持 7Z 以及 Kwrt 的兼容 IPK 设备端首次开机安装。IPK 包的维护脚本不会在 Actions 主机执行；核心包、内核模块和 APK 请从软件源选择。详见 USAGE.md。

## 验证范围

本地与 GitHub 均运行配置、API、文件路径、归档、构建调度等测试。Windows 本地不执行 Linux ImageBuilder；真实构建与隔离 QEMU 开机回归在 Actions 执行。流程与结果见 TESTING.md。

构建通过不代表硬件启动验证通过。请先在虚拟机验证 x86 EFI/Legacy、LuCI、网络和包清单，再用于实机。
