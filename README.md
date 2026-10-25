# OpenWrt Personal Builder

个人固件定制工作台，使用 GitHub Pages 展示配置表单、GitHub Actions 运行 ImageBuilder，无会员、无 VPS。

网页已上线：[打开个人固件工作台](https://hadeschan1985.github.io/openwrt-personal-builder/)。使用方法见 `docs/USAGE.md`，功能地图与自建分析见 `docs/FEATURE-MAP.md`，验证记录见 `docs/TESTING.md` 和 `docs/WORKLOG.md`。

已接入官方 OpenWrt 与校验值固定的 Kwrt x86/64 构建环境。基线引导和 9 组软件组合均完成隔离虚拟机开机、后台登录与 RPC；正式网页直接提交、文件上传、构建、下载与 SHA256 闭环已验证。当前 85 项云端代码/配置检查通过。详细范围及改善建议见 `docs/TESTING.md`、`docs/PACKAGE-TESTING.md`；不等于所有实体设备可安全刷入。

交钥匙完善版新增五组完整软件模板、真实依赖预检、中文自动进度、防重复提交、产物到期提示和 ZIP 本机校验。最新验收见 `docs/RELEASE-6.md`；没有新增账户权限、收费服务或 VPS。

首页已直接显示最近成功的编译结果和私有下载入口，包括从 GitHub 手动发起的构建；未授权时有显眼提示，原有结果无需重编译。见 `docs/HOMEPAGE-RESULTS.md`。

自动跟进上游：每日检测官方稳定版与 Kwrt 25.12 x86/64 的构建器、内核和软件源；通过隔离引导与后台登录回归后才批准，并在已连接的主页添加版本。失败不切换，不自动刷机或覆盖表单；说明见 `docs/UPSTREAM.md`。

接入步骤见 `docs/DEPLOY.md`。推荐公开网页仓库与私有构建仓库分开，避免自己的配置与产物公开。

支持设备/软件搜索、出厂包移除、代理和主题、系统/网络设置、Docker/NAS 组件、7Z/ZIP/TAR 文件覆盖、Kwrt 的设备端 IPK 安装、EFI/Legacy/Ext4/VMDK/ROOTFS 输出。电视盒、任意内核/DTB 和 EMMC 专用打包不在当前版本范围内。

## 本地预览

需要 Python 3.11+ 和 Node.js 20+。

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory site
```

打开 http://127.0.0.1:8765 。

```powershell
node --test tests/*.test.mjs
python -m unittest discover -s tests -p "test_*.py"
```

源代码、构建脚本、Actions 工作流均保存在本目录。GitHub 凭据不写入源码和工作记录。
