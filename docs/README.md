# 文档导航与管理规则

当前产品与工程规则由 Trellis spec 维护；任务和开发记录由 Trellis 管理。这里说明文档职责、资料效力和公开边界，具体任务进度以 task.json 和任务执行计划为准。

## 阅读入口

| 需要了解的内容 | 入口 |
|---|---|
| 安装、启动、基本使用 | [项目 README](../README.md) |
| 会话读取顺序与执行约定 | [AGENTS](../AGENTS.md) |
| 开发规范总览 | [spec 总入口](../.trellis/spec/index.md) |
| 产品流程、术语与范围 | [产品规范](../.trellis/spec/product/index.md) |
| 数据、API、字幕、导入与播放器 | [技术契约](../.trellis/spec/contracts/index.md) |
| 前后端实现约定 | [前端](../.trellis/spec/frontend/index.md)、[后端](../.trellis/spec/backend/index.md)、[工程基线](../.trellis/spec/guides/project-engineering.md) |
| 任务与整理后的会话记录 | [.trellis/tasks](../.trellis/tasks/)、[开发日志](../.trellis/workspace/) |
| 项目许可与第三方文件 | [MIT](../LICENSE)、[第三方声明](../THIRD_PARTY_NOTICES.md) |
| 代码与开发资料的公开边界 | [公开开发与历史封存决定](decisions/2026-10-21-public-development-and-historical-archive.md) |

## 维护位置

| 位置 | 职责 |
|---|---|
| 根 README.md | 产品入口、安装、启动和基本使用 |
| 根 AGENTS.md | 会话读取顺序、执行与验证约定 |
| .trellis/spec/product/ | 当前产品行为、领域术语、范围与验收限制 |
| .trellis/spec/contracts/ | 当前跨层数据、接口与处理契约 |
| .trellis/spec/frontend/、backend/、guides/ | 实现约定与工程方法 |
| .trellis/tasks/ | PRD、设计、执行计划、上下文和结果；按 Trellis 生命周期管理 |
| .trellis/workspace/ | 主动整理的开发日志与索引 |
| docs/decisions/ 中经审阅的公开决定 | 重要选择的理由与影响；当前行为仍由相应 spec 定义 |

一条当前规则只在一个专题维护。修改行为先读产品与技术契约，任务引用规范，不另复制定义。Matt skills 的产出写回 Trellis。文件名使用小写英文 kebab-case；Trellis 固定文件、目录名、状态与归档操作遵循 [workflow.md](../.trellis/workflow.md)及工具实际行为。

## 资料效力与验证

保留“已确认、讨论基线、示例、待定、工程建议”的区别。较晚明确修正优先；示例不成为固定数量、字段或学习规则。产品目标、代码现状和验证结果分别表述，有差异时明确记录。

发现规范缺口，核对当前任务、专题 spec、代码和测试；需要用户决定的语义写回任务。必要规则和限制应在公开仓库中自足表达，新开发无需读取原始讨论或旧任务。已知问题、暂缓检查和未定义范围见[范围与验收边界](../.trellis/spec/product/scope-and-acceptance.md)，整理文档不代表完成实现或验收。

## 公开任务与日志

后续任务及整理后的 workspace 日志默认纳入公开 Git 历史。记录工作目标、有效设计、变更理由、验证证据与限制；区分待讨论、已批准和已完成状态。日志概括会话结果，保留可定位的公开提交与任务引用，不抄录原始私人聊天。

提交前检查任务正文、研究材料、附件、上下文清单和日志：去除密钥、私人信息、本机专有路径及无法公开的原始材料。仅保留项目需要的内容；遇到具体需要保密的资料时单独确定处理方式，而不是默认建立第二套资料库。身份、会话运行态和临时文件沿用忽略规则；运行日志与整理后的开发日志分别处理。

## 历史封存与公开起点

原私有代码仓库及其完整 Git 历史作为档案保留。旧产品／设计正文、里程碑任务、原始讨论、旧 Bootstrap 和日志流水不作为新库的开发依赖，也不转换为新的 Trellis 任务。仍有必要的规则、理由和验收限制单独整理进公开规范或说明，避免仅删历史链接而丢失内容。

首次公开从筛选、验证后的文件状态建立干净初始提交，公开仓库随后成为唯一持续开发代码主库；公开开发不依赖私有资料挂载或文件同步。密钥、数据库、媒体、缓存、运行日志和 work/ 临时产物不进入公开候选。

公开起点只纳入经过筛选和验证的代码、当前规范与必要说明；旧历史材料留在原私有仓库。后续新增任务、整理后的日志和其他文件仍按上述公开检查规则审阅，不能仅因文件位于项目目录中就认定可公开。已知限制继续由[范围与验收边界](../.trellis/spec/product/scope-and-acceptance.md)记录。
