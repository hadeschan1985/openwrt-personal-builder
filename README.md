# OpenWrt Personal Builder

个人固件定制工作台：GitHub Pages 展示网页，GitHub Actions 构建，没有 VPS、会员或收费系统。

- [打开工作台](https://hadeschan1985.github.io/openwrt-personal-builder/?v=20261027-3)
- [日常使用说明](docs/USAGE.md)
- [当前交付范围和限制](docs/DELIVERY.md)
- [本轮测试证据](docs/RELEASE-11.md)

已接入原站当前公开目录的 865 个 Kwrt 设备档案、24 个平台，以及独立的 OpenWrt 官方目录。目录数量不是实体硬件实测数量。N1 已在新的自动验收版本修复；玩客云因构建器校验值不一致继续暂停；另有两个档案仅提供 ROOTFS。

新配置按使用者要求暂用 root / root；可改为私有仓库的 ROUTER_PASSWORD。x86 可逐个映像做虚拟机启动验收；其他设备执行编译及文件校验，界面明确标注未验证实机启动。

固件逐文件独立下载，首页显示私有构建结果、SHA256 和到期时间。令牌仅存在网页内存；授权失效停止自动读取，限流按 GitHub 响应等待，不自动重复提交构建。

自动跟进覆盖官方稳定版和 Kwrt 25.12 x86/64，以及 Kwrt 25.12 的其他平台。x86 通过虚拟机启动和登录后批准；其他平台逐平台实际编译和校验后批准。上游无变化时复用有效证据；新版本和历史配置独立保存，切换由使用者决定。

## 本地预览与检查

需要 Python 3.11+、Node.js 20+；实际 ImageBuilder 构建使用 Linux / Actions。

```powershell
python -m scripts.device_audit
python -m http.server 8765 --bind 127.0.0.1 --directory site
node --test tests/*.test.mjs
python -m unittest discover -s tests -p "test_*.py"
```

网页已包含完整且校验通过的固定快照，部署和本地预览无需读取滚动软件源。自动验收的新版本由私有仓库加载。历史交付说明保留在 docs/RELEASE-*.md，日期和测试数量只对应各自版本。
