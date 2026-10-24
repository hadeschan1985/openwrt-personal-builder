# 个人工作台使用方法

网页：https://hadeschan1985.github.io/openwrt-personal-builder/

构建记录：https://github.com/hadeschan1985/openwrt-personal-builds/actions

## 不输入网页访问令牌的方式

1. 在网页选择设备、明确的固件版本和需要的软件包。
2. 设置后台 IP、主机名、主路由/旁路由、输出格式等。只有当前源中确实存在的软件可选；灰色插件不是已实现的功能。
3. 点“构建新固件”或“查看 / 导出配置”，复制 JSON。
4. 点弹窗内“打开 GitHub 手动构建”，在内部浏览器保持 GitHub 登录。
5. 点 Run workflow，把 JSON 粘贴到 config_json，再点 Run workflow。config_path 保持默认；config_json 留空时将使用示例配置，而不是网页选择。
6. 在构建记录中打开对应任务。完成后，从 Artifacts 下载 firmware 压缩包，解压后核对 SHA256SUMS。

这条路径不需要 VPS，不需要会员，也不需要向网页或聊天发送 GitHub 密码和访问令牌。

## 密码与私人文件

- 网页中的“设置后台密码”使用私有构建仓库的 ROUTER_PASSWORD Secret。
- PPPoE 使用 PPPOE_USERNAME、PPPOE_PASSWORD；Wi-Fi 使用 WIFI_PASSWORD。Secrets 由本人在仓库设置中填写，不发送到聊天。
- 填写 Wi-Fi 名称时必须同时引用 Wi-Fi 密码；不创建开放热点。
- 未启用后台密码的示例配置仅供流程验证。实际联网前应设置可靠密码。
- 初始 Shell 和文件包会进入固件。使用 Secrets 隐藏日志不等于固件内没有私人信息，产物不要公开转发。
- 普通文件包支持 ZIP、TAR.GZ、TGZ；7Z 与压缩包内自动安装 IPK/APK 尚未支持。

## 日志、下载与保留期限

构建失败时先看任务红色步骤和失败日志，不要刷入残缺产物。构建成功后仍须验证启动、LuCI 和网口映射；不自动写盘、刷机或更改现有路由器。

当前成功产物保留 7 天、失败日志产物保留 3 天。需要长期保存时下载到自己的磁盘。网页只是静态界面；关闭页面不会中断 GitHub 已接受的构建。

私有仓库构建使用账号现有 Actions 配额。项目未启用付费套餐、额外付费 runner 或自动充值；不要将个人自用理解为无限算力或永久云端储存。

## 仍未接入的原站能力

Kwrt 专用软件源和代理插件、iStoreOS/路由狗界面、作者外链处理、电视盒/内核/DTB/EMMC 专用打包仍需后续实现。当前网页保留功能清单并明确禁用，不宣称已与 openwrt.ai 全功能等价。
