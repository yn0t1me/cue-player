# 提交清单（用户已确认）

## 工作提交

已确认单个工作提交：`feat: focus player on agent material exports`。

这是一个跨前后端的完整产品变更，接口、数据库与界面需要一起生效。包含应用、迁移、行为测试、README、负责专题的规范和本任务规划/验证资料。

不包含运行数据库、备份、媒体、缓存、日志和 work/ 产物。不提交远程仓库。没有无法识别或来自其他工作的脏文件。

## 文件清单

- `.trellis/spec/backend/database-guidelines.md`
- `.trellis/spec/contracts/data-model.md`
- `.trellis/spec/contracts/http-api.md`
- `.trellis/spec/contracts/index.md`
- `.trellis/spec/contracts/notes-and-anchors.md`
- `.trellis/spec/contracts/publication.md`
- `.trellis/spec/frontend/component-guidelines.md`
- `.trellis/spec/frontend/directory-structure.md`
- `.trellis/spec/frontend/hook-guidelines.md`
- `.trellis/spec/frontend/state-management.md`
- `.trellis/spec/guides/code-reuse-thinking-guide.md`
- `.trellis/spec/guides/cross-layer-thinking-guide.md`
- `.trellis/spec/product/glossary.md`
- `.trellis/spec/product/import-and-collections.md`
- `.trellis/spec/product/index.md`
- `.trellis/spec/product/notes-and-output.md`
- `.trellis/spec/product/reading-experience.md`
- `.trellis/spec/product/scope-and-acceptance.md`
- `.trellis/spec/product/subtitle-workflow.md`
- `.trellis/tasks/10-22-player-agent-export/check.jsonl`
- `.trellis/tasks/10-22-player-agent-export/commit-plan.md`
- `.trellis/tasks/10-22-player-agent-export/design.md`
- `.trellis/tasks/10-22-player-agent-export/implement.jsonl`
- `.trellis/tasks/10-22-player-agent-export/implement.md`
- `.trellis/tasks/10-22-player-agent-export/prd.md`
- `.trellis/tasks/10-22-player-agent-export/task.json`
- `.trellis/tasks/10-22-player-agent-export/validation.md`
- `README.md`
- `backend/app/api/routes/videos.py`
- `backend/app/core/errors.py`
- `backend/app/db/models/__init__.py`
- `backend/app/db/models/transcript_mark.py`
- `backend/app/db/models/transcript_question.py`
- `backend/app/schemas/transcript_marks.py`
- `backend/app/schemas/transcript_questions.py`
- `backend/app/services/transcript_marks.py`
- `backend/app/services/transcript_questions.py`
- `backend/migrations/versions/015_retire_notes_questions.py`
- `backend/tests/test_database.py`
- `backend/tests/test_retired_notes_migration.py`
- `backend/tests/test_retired_subtitle_migration.py`
- `backend/tests/test_source_learning_api.py`
- `backend/tests/test_video_api.py`
- `frontend/src/App.test.tsx`
- `frontend/src/App.tsx`
- `frontend/src/api/videos.test.ts`
- `frontend/src/api/videos.ts`
- `frontend/src/features/transcript/ReaderCollectionPanel.test.tsx`
- `frontend/src/features/transcript/ReaderCollectionPanel.tsx`
- `frontend/src/features/transcript/ReaderNotesControls.test.tsx`
- `frontend/src/features/transcript/ReaderNotesControls.tsx`
- `frontend/src/features/transcript/ReadingNotesWorkspace.tsx`
- `frontend/src/features/transcript/TranscriptExportPanel.test.tsx`
- `frontend/src/features/transcript/TranscriptExportPanel.tsx`
- `frontend/src/features/transcript/TranscriptPanel.test.tsx`
- `frontend/src/features/transcript/TranscriptPanel.tsx`
- `frontend/src/features/transcript/collectionOutput.test.ts`
- `frontend/src/features/transcript/collectionOutput.ts`
- `frontend/src/features/transcript/noteRelations.ts`
- `frontend/src/pages/VideoPage.test.tsx`
- `frontend/src/pages/VideoPage.tsx`
- `frontend/src/styles.css`
- `frontend/src/types/video.ts`

## 确认后的收尾

执行工作提交后，再按 Trellis 流程归档任务、记录整理后的会话日志。归档和日志由工具生成各自的整理提交，不混入产品工作提交。
