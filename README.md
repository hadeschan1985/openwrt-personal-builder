# OpenWrt Personal Builder

个人固件定制工作台，使用 GitHub Pages 展示配置表单、GitHub Actions 运行 ImageBuilder，无会员、无 VPS。

网页已上线：[打开个人固件工作台](https://hadeschan1985.github.io/openwrt-personal-builder/)。使用方法见 `docs/USAGE.md`，验证记录见 `docs/WORKLOG.md`。

已接入官方 OpenWrt 与校验值固定的 Kwrt x86/64 构建环境。官方版 EFI、Legacy、VMDK 已完成隔离虚拟机开机与后台登录；详细验收范围见 `docs/TESTING.md`。虚拟机测试不等于所有实体设备可安全刷入。

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
