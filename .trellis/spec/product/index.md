# Current Product Specifications

Updated: 2026-10-21. Scope: currently implemented product behavior, vocabulary and explicit boundaries. These specs consolidate later product decisions and current implementation; they do not introduce new features.

## Read Before Changing Behavior

1. Read [glossary](glossary.md) for shared terms and [scope](scope-and-acceptance.md) for current/retired/deferred boundaries.
2. Read the topic affected by the task:

| Topic | Authority |
|---|---|
| Import, collections, batches and explicit retry | [Import and collections](import-and-collections.md) |
| Sources, external processing, translation and version publication | [Subtitle workflow](subtitle-workflow.md) |
| Reader tabs, playback, selection, overlay and fullscreen behavior | [Reading experience](reading-experience.md) |
| Favorites, questions, answers, relations and content output | [Notes and output](notes-and-output.md) |

3. For implementation, also read the [frontend](../frontend/index.md) or [backend](../backend/index.md) engineering index. Detailed technical contracts live in [technical specs](../contracts/index.md).

## Evidence and Authority

Topic specs define the effective product behavior and distinguish it from engineering baselines, examples and future proposals. Maintain each rule in its owning topic. Later explicit user decisions override earlier baselines; an example is not a confirmed fixed limit. If code disagrees with an effective decision, document the discrepancy instead of silently changing either behavior or its authority.

Source and test references identify the implementation and verification seams; their presence is not a new successful test or external acceptance run. [Scope and evidence](scope-and-acceptance.md) is the self-contained entry for known limitations and unresolved future behavior. Development does not require archived discussions or old task records.
