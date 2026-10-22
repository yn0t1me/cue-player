# Product Scope and Evidence Boundaries

Updated: 2026-10-21. Scope is a capability baseline, not a second task tracker or new release claim.

## Goal and Current Scope

Context English uses real YouTube material to support understanding and remembering expressions in context. Active expression is the longer-term learning goal; the current product is a personal desktop/local reading-and-notes workspace, not a completed automated learning loop.

Current capabilities: single/multiple/playlist import, manual-first or automatic preference with eligible local-STT fallback, local initial English subtitles, source-based external manual/automatic processing with Chinese and chunks, user-confirmed publication, sentence replay/following, overlay/fullscreen, favorites/notes/manual questions/answers/content output, ordered collections, batch progress and explicit eligible failed-import retry.

## Explicit Boundaries

| Category | Meaning |
|---|---|
| Current | Implemented capabilities above; implementation and acceptance evidence still have scenario-specific limits |
| Retired | In-app cloud subtitle execution/workbench, legacy SRT writes, JSON v1 results and cloud model history/batch/correction storage |
| Deferred | Source-switch/ready-video Reprocess, forcing STT or rerunning normalization on ready videos, automatic note re-anchoring, cross-video expression library/matching |
| Future design | Chapter organization, in-app AI answers, Study Set/LearningItem/KnowledgeNote, recommendation review, targeted practice/evaluation, retelling, discussion, long-term mastery/review/profile and user speech output |

A collection is not a Chapter or Study Set. A saved note is not a future KnowledgeNote; a question's answer is not a practice attempt. Ready is not watched/completed/mastered. Retry of an eligible failed first import is implemented only for that bounded workflow. Source switching and ready-video renormalization remain deferred; current import readiness does not establish completion of those workflows. Existing marks URL routing is retained UI behavior, not permission to restore retired subtitle APIs.

No current automatic playlist synchronization, autoplay-next, persistent resume/watched status, bilingual SRT export, login/multi-user permissions, mobile-specific delivery, desktop package, RAG/agent runtime in the product or Anki workflow is included in the current capability baseline. Public repository preparation is separate from product capability and does not authorize publishing.

## Deferred Checks and Unspecified Behavior

- **Replay timing:** multi-video and long-pause subjective listening checks remain deferred. Source ranges and deterministic timing validation do not establish that every sentence starts or ends naturally; later acceptance needs recorded real playback across those cases. This is an unverified range, not a failed implementation item to resume automatically.
- **Native player controls:** a Chrome report described playback responding to picture clicks while native buttons were invisible. The issue remains deferred and unfixed; static configuration and earlier successful browser checks do not establish its cause or resolution. Reproduction and acceptance requirements live in [player limits](../contracts/player.md#evidence-and-unresolved-limits).
- **External applicability:** use of the application subtitle overlay with YouTube has not been established as externally permitted. Successful technical or user-experience checks do not establish policy approval; see [player limits](../contracts/player.md#evidence-and-unresolved-limits). No policy verification is claimed by this documentation.
- **Future practice and completion:** practice quantity, target prompts, pass criteria, hint levels, skipping/exiting, maximum retries and completion transitions are unspecified. Prior example counts are not fixed requirements. A future item marked learning/completed would not by itself establish long-term mastery.
- **Future in-app learning AI:** complete input/output schemas, prompts, providers/models, retry policy and long-chapter handling remain unspecified. Study-set output, recommendation acceptance, missing/duplicate answer identities and regeneration after user edits require their own scoped design before implementation. Current manual questions/answers do not define these contracts.

Chapter organization, automatic note re-anchoring and a complete learning loop remain outside the current implementation scope. New work must define its acceptance in a Trellis task before extending these boundaries; archived proposals are not prerequisites or automatic authorization. Current API/data questions are routed through [technical specs](../contracts/index.md).

## Acceptance Discipline

Use [engineering evidence guidance](../guides/project-engineering.md#validation-evidence). Test source and old results support understanding but are not new successful runs. Structured result validation does not prove translation quality, lexical fidelity or audio alignment. An overall “no issue” user report is not a per-entry teaching-quality review, and a controlled sample is not every playlist/region/browser or live STT case.

The visible M0.4 badge in `frontend/src/App.tsx` is a stale implementation label, not the current capability definition. This documented discrepancy is not a claim of a code fix. Record each new verification against its actual revision and scenarios in the relevant task; old successful checks cannot close a later report without new evidence.
