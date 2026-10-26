# OpenWrt Personal Builder

个人固件定制工作台：GitHub Pages 展示网页，GitHub Actions 构建，没有 VPS、会员或收费系统。

- [打开工作台](https://hadeschan1985.github.io/openwrt-personal-builder/?v=20261027-1)
- [日常使用说明](docs/USAGE.md)
- [当前交付范围和限制](docs/DELIVERY.md)
- [本轮测试证据](docs/RELEASE-10.md)

已接入原站当前公开目录的 865 个 Kwrt 设备档案、24 个平台，以及独立的 OpenWrt 官方目录。目录数量不是实体硬件实测数量。N1 缺少无线校准包、玩客云构建器校验值不一致，当前明确暂停这两项构建；另有两个档案仅提供 ROOTFS。

新配置按使用者要求暂用 root / root；可改为私有仓库的 ROUTER_PASSWORD。x86 可逐个映像做虚拟机启动验收；其他设备执行编译及文件校验，界面明确标注未验证实机启动。

固件逐文件独立下载，首页显示私有构建结果、SHA256 和到期时间。令牌仅存在网页内存；授权失效停止自动读取，限流按 GitHub 响应等待，不自动重复提交构建。

自动跟进并批准更新目前覆盖官方稳定版和 Kwrt 25.12 的 x86/64。新增其他平台使用固定构建器和包索引指纹；上游变化时停止构建，尚未实现所有平台自动测试后发布更新。

## 本地预览与检查

需要 Python 3.11+、Node.js 20+；实际 ImageBuilder 构建使用 Linux / Actions。

```powershell
python -m scripts.catalog --destination site/data --extend-pinned
python -m scripts.device_audit
python -m http.server 8765 --bind 127.0.0.1 --directory site
node --test tests/*.test.mjs
python -m unittest discover -s tests -p "test_*.py"
```

网页固定版本资料由 Pages 部署流程生成并审计；历史交付说明保留在 docs/RELEASE-*.md，日期和测试数量只对应各自版本。
