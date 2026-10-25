# 验收记录

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
| 配置/归档/请求测试 | 当前本地 29 项 Python（Windows 缺 7-Zip 时跳过 1 项）、15 项 JS；云端安装 7-Zip 后完整执行 | tests/ 与 Validate code and build configuration 工作流 |

早期回归中保留着已定位的失败记录，不能把这些历史工作流描述为全部成功。当前完整引导回归 `40167823669` 已全部成功；扩展矩阵早期 Lighttpd RPC 失败已经通过显式 CGI 路径修复，定向回归 `40168809787` 的 HTTP 和 HTTPS 均成功。

已完成的 9 份报告（13 次实际开机、认证和 RPC 检查）均下载到本地并核对 GitHub 提供的压缩包 SHA256；汇总数据保存在 `verification.json`，其中包含每个引导方式的后台认证及 RPC 返回结果。

## 构建与下载校验

网页专用令牌已按用户批准创建：只选择私有构建仓库，Actions/Contents 读写及必需 Metadata 只读，2026-11-24 到期。真实浏览器连接、读取私有历史和文件包上传通过。正式网页直接提交的 [任务 40170974151](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40170974151) 已成功；不是通过助手连接器代为提交。

产物 firmware-3 为 32,395,224 字节，下载 SHA256 `2900ec86e32d24ca44e49142177bd5f44fe05468386d6057d51aa2df1bca2d7a` 与 GitHub 一致。所有包内 SHA256、EFI/GPT、Legacy/MBR、256 MiB 根分区和所需软件清单通过。ROOTFS 内确认网页上传的测试文件、主机名与签名均存在。该无密码演示固件只验证网站闭环，不用于实体刷机，也没有冒充本次另行开机验证过的产物。

浏览器联调发现 native fetch 接收者问题，已修正并补充回归测试；为避免 Pages 缓存旧模块，脚本和样式使用发布版本标记。390 像素移动端未见横向溢出，模板与构建控件均可使用。

此前官方版真实构建 `40127788108`、扩展输出构建 `40128376512` 成功，产物已经下载并核对包内 SHA256、映像大小、Gzip 完整性、MBR/GPT、根分区边界与所选包清单。Ext4、两种 VMDK 和 ROOTFS TAR.GZ 生成通过。

## 验证边界

- 没有对实体路由器刷机、写盘或修改现有家庭网络。
- 官方目录中的设备数量不是经过本项目逐台实机测试的数量。
- 代理插件的安装和界面可测，但没有用户节点/订阅，不能声明实际代理线路连通。
- USB/无线/WWAN 驱动需要对应实物；虚拟机不能代替全部网卡、无线芯片、蜂窝模块的验证。
- 不承诺第三方滚动软件源永久可用。Kwrt 构建器固定 SHA256，若上游替换构建器，本项目会停止并要求维护更新，而不是静默使用不同二进制。
- 自订 Shell/IPK 的实际行为由其内容决定；内核模块必须与构建环境 ABI 匹配。
