# 软件完善与云端验收 · 2026-10-28

这轮已实现原构建输入归档、断网重建、盒子资源自动跟进、逐型号编译检查、R3D 驱动包名修正和更清楚的错误提示。项目仍使用 GitHub Pages 与 Actions；没有增加 VPS、会员或账户授权。

**当前不能把整个项目标为全部验收完成。** GitHub 已拒绝启动私有仓库的新任务，页面明确提示“recent account payments have failed or your spending limit needs to be increased”。公开仓库的标准 runner 仍可运行。私有网页最后一次重建复验需要等待该限制解除；公开型号补测继续在云端执行。

## 已通过的实际检查

| 范围 | 已观察到的结果 | 证据 |
|---|---|---|
| 代码检查 | JavaScript 85 项、Python 161 项，共 246 项；Linux 零失败、零跳过 | [40622541659](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40622541659) |
| x86 引导 | 官方及 Kwrt 各通过 BIOS、UEFI、VMDK 引导、HTTPS 后台认证与 RPC，共六种引导检查 | [40557756254](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40557756254) |
| 非 x86 代表型号 | 已批准版本含 864 个非 x86 档案，23 个平台各一个代表型号实际编译和文件完整性检查通过 | [40557756328](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40557756328) |
| 盒子已批准资源 | 242 个型号与准确 DTB 匹配，8 个固定内核，10 组实际打包和只读回读通过 | [40557756257](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40557756257) |
| 网页目录与切换 | 8 项实际浏览器检查通过，包括历史资源恢复、TX9、Wavlink 官方完整镜像、无效 IP 和手机布局；没有构建提交 | [40561328990](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40561328990) |
| 玩客云网页闭环 | 网页提交、实际编译、首页逐文件入口、浏览器 SHA256、配置复用及原输入离线重建通过 | 正常 [40560386188](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40560386188)，离线 [40565366694](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40565366694) |
| 盒子网页闭环 | 同上，正常构建及离线重建均通过 | 正常 [40567784641](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40567784641)，离线 [40570142717](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40570142717) |
| Wavlink 网页正常流程 | 网页提交、完整升级镜像、首页入口、实际下载 SHA256 与配置复用通过 | [40567782332](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40567782332) |
| Wavlink 实际断网重建 | 从真实正常构建捕获 156 个包及构建输入，再完全断开外网重建完整升级镜像；实际安装包名及版本与原清单完全一致 | [40620710308](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40620710308) |
| R3D 修正组合 | 替换错误别名 hwmon-drivetemp 为 kmod-hwmon-drivetemp，保留四个风扇与温度监测组件；实际编译及镜像校验通过 | [40570951627](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40570951627) |
| R3D 自动复验与发布 | 新平台资源的修正组合实际编译、四个温度/风扇组件、镜像校验及独立元数据发布均通过；旧指纹证据仍保留 | [40622541784](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40622541784) |
| R3D 本机界面回归 | 真实页面、固定本地 API 资料：首次点击、输入框失焦、指定包名修改、其他所有配置逐字段保持、避免重复应用、新旧证明并存及历史配置恢复均通过；未调用真实构建 API | outputs/release13-r3d-local-ui.json |

代码测试、界面回归、实际编译与引导验收分别记录，不能相互替代。当前 actionlint 1.7.12 尚不识别 GitHub 新增的 concurrency.queue 字段；只排除这一个已核对提示，其余工作流检查通过。Windows 的两项 Linux 工具检查已由 Linux CI 补齐。

Wavlink 的公开断网测试使用全新临时配置和本地归档回放，没有复制私有账户资料，也没有执行私有 Release 的下载和网页调度。因此它证明离线编译修复有效，不能冒充“私有网页完整复验已通过”。

## 逐型号测试的真实状态

首轮 [40557770783](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40557770783) 已完整检查 863 个公开非 x86 档案：738 个默认组合通过，125 个未通过。其中 122 个在测试期间检测到上游资源变更，2 个因下载中断，另 1 个是 R3D 默认包名缺陷。R3D 修正组合的成功证据单独保存，默认组合失败不会被改写为成功。

补测 [40620075046](https://github.com/hadeschan1985/openwrt-personal-builder/actions/runs/40620075046) 已开始。有效证据必须同时匹配构建规则与平台资源指纹；上游内容变化后需要重新测试，不能沿用过期的通过结论。任务完成后自动保存报告；剩余批次、瞬时网络错误和变化中的上游资源仍可能产生未通过项。

玩客云的私有作者构建器不在公开编译任务中使用。其公共软件索引当前返回 404，公开型号补测已经与这一私有平台隔离；私有上游更新在资料不完整时继续保留此前已批准版本。

## 已实现的交付与更新行为

首页显示最近成功构建，各镜像分别下载，并提供文件 SHA256、本机校验、原配置复用与历史记录。较新的失败或排队任务不会隐藏最后一次成功结果。队列采用有界顺序等待，防止连续提交时较早的等待任务被替换。

成功构建会在私有仓库保存原始 ImageBuilder、实际使用的软件包、原构建代码及配套打包资源。盒子还保存固定源码和内核；玩客云保存作者打包器和引导模板。旧输入和旧固件不覆盖、不自动删除。没有输入快照的早期记录不会凭空获得离线重建按钮。

离线构建保留本机回环通信供 fakeroot 使用，同时验证外网不可达且编译进程没有 GitHub 令牌。APK 兼容层只整理解出的本地包时间和文件名，文件名读取自包内元数据，并核对软件包字节未变；原归档与原构建代码文件保持原样，兼容层摘要单独记入报告。实际包版本不同则停止交付。正常与离线镜像可能因生成时间和随机字段具有不同 SHA256，不承诺逐字节复现。详见 [REBUILD.md](REBUILD.md)。

上游每天分别检查 x86、多型号和盒子；发生变化后须实际编译、打包或引导验收，通过后才批准。旧目录与旧配置保留，新版本由使用者主动选择。未知发行系列或不认识的资料格式不能放行。R3D 修正同样按精确平台指纹记录，旧证据不能用于不同的新资源。

## 仍需完成或依赖外部环境

| 项目 | 当前边界 |
|---|---|
| 私有网页最后一次复验 | Wavlink 离线编译修复已通过公开实际测试；通过私有网页重新提交、完成重建及读取新记录，受 GitHub 账户限制阻塞 |
| 公开型号补测 | 云端任务仍在执行，以最终逐型号报告为准；不宣称所有型号均已通过 |
| 最新上游批准 | 最新定时任务受账户限制或上游索引 404 影响，继续保留此前已批准版本；不能声称当前上游均已升级到最新 |
| 四个盒子 DTB | kickpi-k11c-v12、smart-am40、station-m1、rk3318-box 仍缺准确资源，继续排除 |
| 跨未来大版本 | 已实现候选检测和重新验收规则；未发布的未来系列没有实测结论 |
| ESXi 与实体硬件 | 尚无环境，未创建虚拟机或刷机；无线、USB/WWAN、真实代理线路等仍需实际设备 |

后续获得 ESXi 后按 [ESXI-ACCEPTANCE.md](ESXI-ACCEPTANCE.md) 接手验证。现有 QEMU 引导证据不冒充 ESXi 验收。没有修改家庭网络、现有虚拟机、账户计费、Secrets 或令牌权限。
