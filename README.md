# OpenWrt Personal Builder

个人固件定制工作台，使用 GitHub Pages 展示配置表单、GitHub Actions 运行 ImageBuilder，无会员、无 VPS。

项目状态和验证记录见 `docs/WORKLOG.md`。本地基础版已制作并验证，尚未发布到 GitHub，也尚未运行真实云构建。

接入步骤见 `docs/DEPLOY.md`。推荐公开网页仓库与私有构建仓库分开，避免自己的配置与产物公开。

目前支持官方 OpenWrt ImageBuilder；Kwrt 专属软件源、电视盒和包内 IPK/APK 安装等高级能力尚未接通，界面会明确标识。

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
