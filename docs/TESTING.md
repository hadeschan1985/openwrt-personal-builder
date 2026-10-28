# 验收记录

当前功能范围见 [DELIVERY.md](DELIVERY.md)。2026-10-28 的 [云端代码检查 40622541659](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40622541659) 已通过 JavaScript 85 项及 Python 161 项，共 246 项、零失败、零跳过。Windows 本地两项外部工具检查由 Linux CI 补齐。实体设备暂不可用，只完成云端范围；固件运行与流程验收另以 [RELEASE-13.md](RELEASE-13.md) 中各自的实际报告为准。

以下保留历史版本的验收范围与测试数量。此前玩客云、盒子和 23 个非 x86 平台完整回归见 [RELEASE-12.md](RELEASE-12.md)；这些历史成功记录不代替新代码、新资源的独立验收。

本页只列已经观察到的结果；测试中的项目不算完成。所有云端开机测试使用临时密码/SSH 密钥，虚拟机不能访问外网，不共享宿主机目录；测试固件和密钥不作为可用产物上传。

## 已通过

| 项目 | 结果 | 证据 |
|---|---|---|
| 官方 SquashFS · EFI/UEFI | 实际开机、首次开机设置、HTTPS 后台登录、密码认证、RPC | [完整开机回归](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40167823669) 中 official 子任务成功 |
| 官方 SquashFS · Legacy BIOS | 同上 | 同一 official 子任务 |
| streamOptimized VMDK · BIOS | 实际在 QEMU 启动，不等于 ESXi 已测 | 同一 official 子任务 |
| 官方 Ext4 旁路由 | .253 管理 IP、网关、DHCP 关闭、LAN IPv6 通告关闭、HTTP 后台登录、RPC | [扩展回归](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40167403974) 中 official/side-ext4 子任务成功 |
| 官方 Nginx · HTTP | 实际开机、后台登录、密码认证 | 同一扩展回归中 official/nginx 子任务成功 |
| 官方 Nginx · HTTPS | 实际开机、后台登录、HTTP JSON-RPC | 回归 40167403974 的 official/nginx-https 子任务成功 |
| Kwrt SquashFS · EFI/Legacy/原生 VMDK | 三种方式实际开机、NAS 配置、PassWall/主题、自订 IPK 设备端安装、密码/HTTPS 登录/RPC | [完整开机回归 40167823669](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40167823669)，两个来源均成功 |
| Kwrt iptables | 移除 firewall4，legacy 后端，首次开机配置与后台通信 | 回归 40167403974 的 kwrt/iptables 子任务成功 |
| Kwrt Lighttpd · HTTP/HTTPS | 实际开机、密码登录及 CGI JSON-RPC 均成功 | [定向回归 40168809787](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40168809787)，两个子任务均成功 |
| Kwrt Ext4/1 GiB + Docker/USB/WWAN | 实际开机，Docker daemon 可响应，驱动和蜂窝组件已安装，深色主题、NAS/IPK、登录/RPC | 回归 40167403974 的 kwrt/features 子任务成功；不等于 USB/蜂窝实物已测 |
| 配置/归档/请求测试 | 当前 38 项 Python（Windows 缺 7-Zip 时跳过 1 项）、25 项 JS；云端完整执行 63 项 | tests/ 与 Validate code and build configuration 工作流；日志确认 40193188058 |

早期回归中保留着已定位的失败记录，不能把这些历史工作流描述为全部成功。当前完整引导回归 `40167823669` 已全部成功；扩展矩阵早期 Lighttpd RPC 失败已经通过显式 CGI 路径修复，定向回归 `40168809787` 的 HTTP 和 HTTPS 均成功。

已完成的 9 份报告（13 次实际开机、认证和 RPC 检查）均下载到本地并核对 GitHub 提供的压缩包 SHA256；汇总数据保存在 `verification.json`，其中包含每个引导方式的后台认证及 RPC 返回结果。

## 构建与下载校验

网页专用令牌已按用户批准创建：只选择私有构建仓库，Actions/Contents 读写及必需 Metadata 只读，2026-11-24 到期。真实浏览器连接、读取私有历史和文件包上传通过。正式网页直接提交的 [任务 40170974151](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40170974151) 已成功；不是通过助手连接器代为提交。

产物 firmware-3 为 32,395,224 字节，下载 SHA256 `2900ec86e32d24ca44e49142177bd5f44fe05468386d6057d51aa2df1bca2d7a` 与 GitHub 一致。所有包内 SHA256、EFI/GPT、Legacy/MBR、256 MiB 根分区和所需软件清单通过。ROOTFS 内确认网页上传的测试文件、主机名与签名均存在。该无密码演示固件只验证网站闭环，不用于实体刷机，也没有冒充本次另行开机验证过的产物。

浏览器联调发现 native fetch 接收者问题，已修正并补充回归测试；为避免 Pages 缓存旧模块，脚本和样式使用发布版本标记。390 像素移动端未见横向溢出，模板与构建控件均可使用。

此前官方版真实构建 `40127788108`、扩展输出构建 `40128376512` 成功，产物已经下载并核对包内 SHA256、映像大小、Gzip 完整性、MBR/GPT、根分区边界与所选包清单。Ext4、两种 VMDK 和 ROOTFS TAR.GZ 生成通过。

## 后续软件组合验收（同日追加）

用户要求继续添加各种定制软件进行调试后，新增 9 组软件组合，覆盖 25 种明确指定的软件/协议/代理包。全部实际构建、开机、设备内包数据库、后台密码登录与 RPC 通过；另重新完成 6 次 EFI/Legacy/VMDK 基线开机。11 份报告下载后 SHA256 均匹配。

本轮修复了自订包框绕过防火墙要求、HomeProxy Pro 漏检、主题/代理同时添加移除、冲突插件无法取消等问题；新增前后端检查已发布。详见 `PACKAGE-TESTING.md` 和 `software-qa-verification.json`，不把插件集成通过说成用户真实线路/实物验证通过。

## 验证边界

交钥匙完善版增加了实际依赖预检、双核心软件组合、中文自动跟踪和 ZIP 本机校验。正式网页任务 40193155017 已成功，产物完整性与页面跟踪、正确/错误 ZIP 拦截均验证；该单独网页产物不冒充另行开机验收。最新九组回归的最终状态与证据以 RELEASE-6.md 为准。

新回归 40192493869 已全部成功：九组各完成一次 BIOS 开机、安装/移除包数据库、密码登录及 HTTPS/RPC 验证；另有缺包负向检查成功。10 份报告均下载并核对 SHA256，汇总见 release6-verification.json。本轮新增 9 次开机；加上此前 13 与 15 次，累计 37 次隔离开机实例（含重复组合/基线，不是 37 台实体设备）。

- 没有对实体路由器刷机、写盘或修改现有家庭网络。
- 官方目录中的设备数量不是经过本项目逐台实机测试的数量。
- 代理插件的安装和界面可测，但没有用户节点/订阅，不能声明实际代理线路连通。
- USB/无线/WWAN 驱动需要对应实物；虚拟机不能代替全部网卡、无线芯片、蜂窝模块的验证。
- 不承诺第三方滚动软件源永久可用。Kwrt 构建器固定 SHA256，若上游替换构建器，本项目会停止并要求维护更新，而不是静默使用不同二进制。
- 自订 Shell/IPK 的实际行为由其内容决定；内核模块必须与构建环境 ABI 匹配。
