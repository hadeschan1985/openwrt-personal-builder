# 下载与本机校验完善版 · 2026-10-26

## 每个映像单独下载

新 x86 构建将 EFI IMG、Legacy IMG、EFI VMDK、Legacy VMDK 分成四个独立产物，每个产物只含一个映像。Kwrt 原生 VMDK ZIP 与官方转换的 VMDK 都分别处理两种启动方式。ROOTFS、日志与清单另列；未选择的格式不生成下载。发现同组有多个映像会停止，不偷偷重新合成大包。其他架构保留原方式。

私有收藏的原始文件现在直接显示在首页，每项都有大小、SHA256、单文件下载和本机校验。日志与摘要折叠，总包作为备用保留。未填写配置、原始产物、旧收藏与 Secrets 不会被改动。

## 旧包无需重新编译

旧总包在 GitHub 内核对完整 ZIP SHA256，限制数量、体积和文件名，拒绝路径穿越、链接、加密、重复项、额外未校验文件与清单冲突；随后逐文件核对原 SHA256，并分别保存到私有 Release。没有执行固件或压缩包内脚本，原总包不删除。仍遵守最多五个收藏、每版 1.5 GiB 的限制。

第 5 次构建的 984,454,128 字节总包已在[拆分任务 40322459463](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40322459463)完成。四份映像分别为 246,179,407、246,182,209、245,964,606、245,965,818 字节，另有日志与清单。[私有下载入口](https://github.com/hadeschan1985/openwrt-personal-builds/releases/tag/personal-build-5-40198910508)需要 GitHub 访问该仓库的原有授权。这次只是校验与拆分，未增加启动或实机验收结论。

首次拆分在创建收藏时遇到 GitHub 对旧工作流提交的权限限制，未创建残缺公开发布。已调整为将收藏标签指向现有 main，原固件代码提交明确记录在说明及构建记录中；无需新增 Workflows 写权限。一次性的私有请求文件仅包含构建 ID，经格式校验后触发；不属于定时重复构建。已有完整收藏不覆盖。

## 最大 4 GiB 的本机校验

校验改为同源独立 Worker，每次最多读取 1 MiB，避免把整个固件一次载入页面。窗口区分 ZIP 与具体文件，先检查大小，再计算 SHA256，显示进度并可停止。关闭窗口、断开授权、切换仓库或启动另一项会停止旧任务；迟到结果不能覆盖新任务或恢复已清除的私人显示。文件不上传，Worker 不接收 GitHub 令牌或下载 URL。

哈希实现固定为 [noble-hashes 2.4.0](https://github.com/paulmillr/noble-hashes)，只使用 SHA256。五个运行/许可文件从 npm 包原样复制，包的 SHA512 完整性和文件 SHA256 均校验并记录于 `site/vendor/noble-hashes-2.4.0/SOURCE.json`；保留 MIT 许可，无运行时 CDN 或自动拉取脚本。未增加托管服务、会员、付费资源、账号权限或新令牌。

## 验证

- [代码检查 40322522626](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40322522626)：JS 54 + Python 79，共 133 项全部通过，Linux 无跳过。本地 Windows 缺 OpenSSL CLI / 7-Zip 的两项仍由 Linux 执行。
- [两组打包验收 40286015817](https://github.com/hadeschan1985/openwrt-personal-builds/actions/runs/40286015817)：原生 ZIP 和转换 VMDK 两类，各四个独立测试下载；断言每个只有一个原始文件，校验值不变。测试明确标记为合成材料，不冒充新生成固件或新增开机次数。
- 实际浏览器读取 314,572,960 字节（300 MiB）合成 ZIP，结果与独立 Python SHA256 一致；257 MiB 的自动测试禁止整文件读取并检查每次读取上限。真实后台线程与 Node 原生 SHA256 在边界长度、随机数据、空文件上互相核对。
- 正确文件通过；错大小即时拒绝；同大小损坏文件拒绝；停止和关闭进行中的大文件任务、断开后清理私人显示均通过。手机 390 像素视口中内容/滚动宽 375，校验窗口约 341，无横向溢出。四入口及手机页面使用本地模拟连接和真实下载元数据预览，未创建或使用新的私人令牌。

4 GiB 是输入限制，本轮实际浏览器大文件验收为 300 MiB，没有声称已经实读 4 GiB。校验完整性不等于实体设备、代理线路或任意虚拟机宿主机已经可用。既有固件的启动验证范围见 RELEASE-7.md / RELEASE-8.md，本轮没有重新编译或刷机。

GitHub 旧提交限制依据：[官方变更说明](https://github.blog/changelog/2023-11-02-github-actions-enforcing-workflow-scope-when-creating-a-release/)。
