# Context English

以真实 YouTube 内容为语料，逐句阅读与回听字幕，收藏值得记忆的表达，记录个人备注、问题和解答。

当前为本地 React/FastAPI/SQLite 应用，支持单视频、多链接及播放列表导入、视频合集、字幕来源选择、本机 STT fallback、外部字幕处理、原句／词块与中文显示、学习字幕全屏、笔记复制和 Markdown 导出。

字幕首次生成在本机完成。后续可复制分来源任务到外部 AI，带回来源 JSON v2 结果，预览后确认发布；应用不调用云端字幕或问答模型。收藏和问题保留创建时的字幕版本，发布新字幕不会自动迁移旧笔记。

## 文档入口

- [产品流程与范围](.trellis/spec/product/index.md)
- [技术契约](.trellis/spec/contracts/index.md)与[工程约定](.trellis/spec/guides/project-engineering.md)
- [开发规范总入口](.trellis/spec/index.md)与[AI 开发约定](AGENTS.md)
- [文档导航与开发记录规则](docs/README.md)

## 安装（WSL）

以下从仓库根目录执行。Python 版本以 backend/pyproject.toml 为准，Node/npm 以 .nvmrc 和 frontend/package.json 为准；保留两端锁文件。

```bash
source "$HOME/.nvm/nvm.sh"
nvm use
command -v node npm
# 应指向 WSL 的 /home/.../.nvm/，而不是 Windows 的 /mnt/...。
[ -f .env ] || cp .env.example .env
cd backend
uv sync --locked
```

在 backend/ 准备本地 STT 模型并执行新环境迁移：

```bash
HF_HUB_DISABLE_XET=1 HF_HUB_DOWNLOAD_TIMEOUT=1800 HF_HUB_ETAG_TIMEOUT=60 uv run --locked hf download Systran/faster-whisper-base.en --local-dir ../data/cache/faster-whisper/base.en --max-workers 1
uv run --locked python -m app.services.transcript.stt_runtime
uv run --locked alembic upgrade head
cd ../frontend
npm ci
```

当前 schema 为 `014_retire_legacy_subtitles`。已有旧数据时先备份并核对迁移前提；014 会拒绝未处理的退役数据，不负责替用户自动清理。开发迁移验证使用[隔离数据库](.trellis/spec/guides/project-engineering.md#database-and-runtime-safety)。应用启动不自动建表或执行迁移。

根 .env.example 提供配置示例，后端读取根 .env。字幕工作流不需要云模型密钥；STT 需要预先下载的本地模型，默认 CPU/int8，导入时不隐式下载模型。数据库、VTT、临时音频和模型缓存放在 data/，不提交 Git。

## 启动

分别打开两个 WSL 终端，从仓库根目录执行。

后端：

```bash
cd backend
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```bash
source "$HOME/.nvm/nvm.sh"
nvm use
cd frontend
npm run dev
```

Windows 浏览器打开 [应用页面](http://localhost:5173)。[健康接口](http://localhost:8000/api/health)仅表示后端可响应；[接口文档](http://localhost:8000/docs)展示运行中 API。默认前端端口固定为 5173，占用即报错；使用其他本地端口时同时核对后端 CORS_ORIGINS。两个终端分别按 Ctrl+C 停止服务，更新后端代码后需重启后端。

## 使用与验证

导入时选择“人工字幕优先”或“自动字幕”；所选策略没有合格英文字幕时使用本机转写，发现／下载故障不会伪装为无字幕。重复链接打开原视频，保持原来源；失败项通过显式重试处理。合集与批次分别用于长期视频组织和本次导入进度。

视频就绪后可点击整句回听，手动滚动暂停跟随；选中文字可收藏、做笔记或提问，三类内容在阅读页同位切换。解答由用户手动填写或从外部 AI 带回。字幕管理按实际来源提供外部处理指令，STT 或时间证据不足时保留基础英文阅读并说明限制。Raw 和当前学习稿分别支持英文 SRT 导出；SRT 写入和 JSON v1 已退役。

后端测试（backend/）：

```bash
uv run --locked pytest -q
```

前端测试与类型／构建检查（frontend/，使用上述 WSL Node 环境）：

```bash
npm test
npm run build
```

真实 YouTube 播放、外部 AI 文字质量及 STT 表现需要单独验证，不能由健康检查或模拟测试替代。当前限制和暂缓验收见[范围与证据](.trellis/spec/product/scope-and-acceptance.md)。

## 开发

开发从 [AGENTS.md](AGENTS.md)、当前 Trellis 任务和相关 spec 开始。任务与整理后的开发日志默认随代码共享；Matt skills 按阶段辅助，产出写回 Trellis。公开仓库应包含开发所需的全部规则和说明，旧资料及旧 Git 历史封存于原私有仓库，不作为后续开发前提。维护位置和资料边界见[文档规则](docs/README.md)。

本仓库的开发依据为当前代码、spec、任务和整理后的日志。历史资料的封存与公开记录规则见[文档规则](docs/README.md)。

## 许可证

项目原创代码与文档采用 [MIT 许可证](LICENSE)，允许商用、修改和闭源分发，并要求保留版权与许可声明。

随库的 Trellis 开发工具保留其上游授权，不由本项目重新授予 MIT；具体来源、文件范围和许可副本见 [第三方声明](THIRD_PARTY_NOTICES.md)。依赖包、单独下载的模型和用户媒体遵循各自授权。
