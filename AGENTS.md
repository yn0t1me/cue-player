<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

# 项目开发与文档约定

## 会话与任务

开始工作先读 README.md，检查 Git 状态；已有匹配任务先复用，按 `.agents/skills/trellis-start/SKILL.md` 加载 Trellis 会话状态、工作流阶段及相关规范索引，再读取当前任务材料。
计划、上下文、执行状态、验证结果和归档统一使用 Trellis，步骤以 `.trellis/workflow.md` 为准。一次执行一个已授权的工作项；用户要求阶段性停下时，完成该项后停下。
Matt skills 按用户指定的阶段辅助讨论、设计、实现或审查，产出写回相应 Trellis 任务或规范，不另建任务与进度体系。
已完成工作、暂缓事项和未来设计仅提供背景；实施范围由当前任务及用户授权确定。

## 规范与上下文

规范总入口为 `.trellis/spec/index.md`。修改产品行为或数据语义前读取 product/，修改 API、字幕、导入或播放器边界前读取 contracts/；实现时读取 frontend/、backend/ 和相关 guides/。完整阅读当前任务引用的相关专题；文档维护位置及公开记录规则见 `docs/README.md`。
每条当前规则只在负责该主题的 spec 维护，任务引用规范。保留“已确认、讨论基线、示例、待定、工程建议”的区别；示例不视为用户逐项确认，代码现状与已确认目标有差异时明确记录。
发现规格遗漏或冲突，先核对当前任务、专题 spec、代码与测试；将缺口和建议写入任务，涉及学习流程或核心数据语义时向用户明确差异并取得范围决定。后续开发所需规则须在公开仓库内完整表达。
历史资料及完整旧 Git 历史由原私有仓库封存，不作为新会话、子代理或 worktree 的必读上下文。旧任务保持历史地位；必要结论整理进当前规范或公开说明，不转换成新的 Trellis 任务。

## 实施与验证

项目操作在 WSL 本仓库执行，运行数据在 `data/`；保持 React/FastAPI/SQLite 既定架构。
完成工作先验证，再更新 Trellis 任务状态；有实际结果后记录变更、证据与限制，同步相关规范及必要决策记录。
区分文档检查、样例测试与真实 YouTube 验收；外部链路未验证时明确记录限制。
后续任务与整理后的开发日志默认公开，提交前按 `docs/README.md` 检查内容。密钥、数据库、媒体、缓存、运行日志与 `work/` 临时产物不提交 Git。
