# N1 校准包兼容依据

固定参考：iStoreOS 提交 `283d02639c740f8ae6e9425b48be8c61f152c6b8`。

- [N1 映像定义](https://github.com/istoreos/istoreos/blob/283d02639c740f8ae6e9425b48be8c61f152c6b8/target/linux/amlogic/image/meson.mk) 明确依赖 `brcmfmac-nvram-43455-sdio-generic`。
- [固件包定义](https://github.com/istoreos/istoreos/blob/283d02639c740f8ae6e9425b48be8c61f152c6b8/package/firmware/linux-firmware/broadcom.mk) 明确将 `brcmfmac43455-sdio.txt` 链接到同目录中的 `brcmfmac43455-sdio.raspberrypi,4-model-b.txt`，并依赖实际数据包 `brcmfmac-nvram-43455-sdio`。
- [Kwrt N1 导入来源](https://github.com/kiddin9/Kwrt/blob/25.12/devices/amlogic_meson/diy.sh) 是 iStoreOS 的 `istoreos-25.12` 分支。

本项目只恢复这条已记录的上游链接，不另行提供或修改校准数值。兼容包没有安装脚本，实际校准文件仍来自选定的 Kwrt 软件源。映像生成后必须同时检查链接目标和非空的实际数据文件。此修复仅允许 `amlogic/meson` 的 `phicomm_n1`，不会应用到其他设备。

旧固定版本的暂停标记保留。仅新的自动验收版本可以采用此修复，而且必须完成真实 ImageBuilder 构建和文件完整性检查后才批准。通过上述检查不代表已经验证无线收发、射频性能或实体开机。
