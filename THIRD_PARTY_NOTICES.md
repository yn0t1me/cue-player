# 第三方材料与许可证

Context English 的原创部分使用根 [MIT License](LICENSE)。本文件列出的第三方材料保留其原有版权和许可，不因根许可证而重新授权为 MIT。

## Trellis 开发工具

本仓库包含由 [Trellis 0.6.17](https://github.com/mindfold-ai/Trellis/tree/833a5846d18ad7a5ccd8c41c876d89cc936f5fd9) 安装的脚本、skills、hooks、代理配置和工作流，以及 AGENTS.md 的 Trellis 托管区。

- 上游版权：Copyright (C) 2026 Mindfold LLC。
- 上游完整 [LICENSE](LICENSES/trellis/LICENSE) 与 [COPYRIGHT](LICENSES/trellis/COPYRIGHT) 随库保留，来源和校验见 [Trellis 说明](LICENSES/trellis/README.md)。
- [文件与区域清单](LICENSES/trellis/source-inventory.json)区分生成文件、托管区及安装元数据。项目自写的 spec、任务和日志不因位于 `.trellis/` 而统一归入第三方工具许可。
- 上游 LICENSE 是 AGPL v3 文本，COPYRIGHT 使用 v3-or-later 措辞，而该版本 [CLI 元数据](https://github.com/mindfold-ai/Trellis/blob/833a5846d18ad7a5ccd8c41c876d89cc936f5fd9/packages/cli/package.json)标为 `AGPL-3.0-only`。这里保留原声明，不擅自消解该差异，也不声称获得模板复制例外。

这些材料属于开发工具；本说明不将其重新授权为 MIT，也不据此断言独立应用源码自动适用 AGPL。

## 安装依赖、二进制与模型

前后端依赖及精确版本由 [Python 锁文件](backend/uv.lock)和 [Node 锁文件](frontend/package-lock.json)记录，各依赖保留自己的许可。源码仓库不随附 node_modules、Python 虚拟环境、构建产物、FFmpeg 或模型权重；安装后取得的组件不能统一视作本项目的 MIT 内容。

特别是 yt-dlp 的 Python 包与捆绑可执行文件可能有不同的随附许可；PyAV 轮子包含 FFmpeg 库，其许可取决于实际构建；转写模型也有独立来源与授权。未来分发安装包、容器或模型时，应按实际随附内容保留所需许可、声明及源码获取信息。本文件是来源与边界说明，不是完整传递依赖或二进制分发审计的完成声明。
