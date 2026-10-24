# 更名与公开发布验证

日期：2026-10-24。当前状态：更名、公开创建和首次推送已完成，正在归档整理。

## 历史公开检查

对将保留的 main 五个提交可达内容执行检查：369 个 blob，合计 2,654,778 字节。

- 枚举历史路径，未发现被提交的实际 .env、数据库、密钥文件、运行 data/work/cache、依赖目录、日志或媒体。
- 无大于 5 MB 的文件。
- 扫描私钥标记、GitHub/OpenAI/Google/AWS 常见凭证形态、带口令 URL 和本机专有绝对路径。
- 唯一模式命中为 backend/tests/test_youtube_playlists.py 的无效 URL 测试样例；已核对是 user/password 占位文本，不是真实账号凭证。
- 记录扫描范围与误报核对，不将模式扫描等同于完整外部安全审计。
- 原创 MIT、Trellis 原始许可及版权声明、来源清单均存在；此次仅更改产品名称，不重新解释第三方许可。

## 更名与验证

- 页面品牌、HTML title、OpenAPI 标题、Markdown 下载前缀、两个项目名及锁文件根项目条目更新为 Cue Player / cue-player。
- README、THIRD_PARTY_NOTICES 开头和四份当前规范更新品牌；原始 LICENSE/第三方许可正文、历史任务和日志不变。
- 前端 152 tests passed，tsc + Vite build passed。
- 后端 test_health.py 1 test passed，覆盖 OpenAPI title；uv sync --locked 通过。
- 独立复查核对 17 个文件，无修复项。逆转根名称替换后，两个锁文件与基线精确相同；导出器除文件名前缀外逐字节不变。
- 本次未重新运行此前475项后端完整回归或真实 YouTube 验收，不以历史结果代替新检查。
- 后端已正常重启，实际 /api/health 返回 ok、OpenAPI title 为 Cue Player，Vite HTML title 为 Cue Player；无数据库迁移或清理。

## 当前文件公开检查

对当前将提交的版本化/未忽略文件进行同一组检查，未发现实际凭证、被跟踪运行数据或本机专有绝对路径；仍只有已经核对的测试占位 URL 命中。忽略目录中的备份、数据库、浏览器产物、日志不纳入发布。

## 发布结果

- 用户确认具体提交清单后，工作提交 f38a33d（chore: rename project to Cue Player）已完成，并快进合并至 main。
- 首次推送前对 main 六个提交、393 个 blob（2,867,530 字节）再次执行历史检查，仍仅有已核对的测试占位 URL 命中，无运行数据、凭证模式或大文件异常。
- 已新建公开仓库：https://github.com/yn0t1me/cue-player 。GitHub API 确认 visibility=public、private=false、default_branch=main，识别根许可证为 MIT；第三方许可边界仍以 THIRD_PARTY_NOTICES.md 为准。
- origin 配置为新仓库 HTTPS 地址；main 首次推送成功，并设置 origin/main 上游。
- GitHub API 返回 main SHA 为 f38a33dd993b39652996dc61ddec89e85aefc16b，与首次推送后的本地 main 完全一致。
- 已确认原 yn0t1me/context-english 仓库仍为 private；未更改其设置或内容。
- 此次仅发布 main，没有 force push、镜像推送、其他分支/标签发布或历史重写。
- 任务归档与整理后的会话日志将追加推送，并在最终回复前复核本地/远程一致性。

## 验证边界

名称、元数据和公开发布均有实际结果；此任务不包含新的数据库迁移、真实 YouTube 稳定播放验收、外部 Agent 教学质量验收或外部安全审计认证。
