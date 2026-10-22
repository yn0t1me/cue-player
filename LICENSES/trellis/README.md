# Trellis 第三方来源

上游：[mindfold-ai/Trellis](https://github.com/mindfold-ai/Trellis)，版本 0.6.17，固定提交 `833a5846d18ad7a5ccd8c41c876d89cc936f5fd9`。版权归 Mindfold LLC，原声明见 [COPYRIGHT](COPYRIGHT)，完整许可见 [LICENSE](LICENSE)。这些文件从固定提交原样取得，未改写其内容。

## 许可与原创部分的边界

上游材料不适用本项目根 MIT 的重新授权。上游 COPYRIGHT 的 v3-or-later 与 CLI package.json 的 `AGPL-3.0-only` 表述差异按原文保留；本说明不替上游选择 SPDX 变体，也不宣称找到模板许可例外。

[清单](source-inventory.json)列明 86 个安装清单路径、生成清单中的 SHA-256 和本次本地文件校验值；包括 scripts、skills、hooks、工作流和代理配置。核对“本地字节与生成清单一致”不等于对这 86 个文件逐一独立证明上游模板字节一致，清单明确记录这一证据限制。

额外材料单独列出：`.trellis/.gitignore`、AGENTS.md 的 `TRELLIS:START` 至 `TRELLIS:END` 托管区，以及 `.trellis/.version`、`.trellis/.template-hashes.json` 安装元数据。`.gitignore` 已与固定提交模板逐字节比较；AGENTS 托管区已与固定提交模板比较，比较时仅忽略两端空白。AGENTS 托管区以外的项目约定不属于这一复制区域。

项目自写的 `.trellis/spec/`、任务及日志不在这份生成工具清单中，不能仅按目录名套用上游许可。若将来修改或升级这些工具，应更新来源、变更说明与校验记录。

## 原文校验

| 文件 | SHA-256 |
|---|---|
| LICENSE | `d8a6cc31abc16b6748c7a21f21611f5a1ec33f67d22ca23d7da1c19b95496bee` |
| COPYRIGHT | `c9640ad1fcdc27ffa127974f796489c61ed475de10c9b47d3e644aced219ca15` |

下载地址、字节长度和额外核对来源见 [upstream-sources.json](upstream-sources.json)。校验针对保存的原文，许可证和版权文本保持各自原始措辞。
