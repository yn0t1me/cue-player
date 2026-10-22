# Reuse and Consistency Guide

Applies to project code and documentation. Search the relevant source/spec before adding a helper or repeating a contract.

## Existing Ownership Seams

| Need | Existing owner |
|---|---|
| HTTP transport and safe API errors | `frontend/src/api/client.ts` |
| Selection identity / question relations | `frontend/src/features/transcript/noteRelations.ts` |
| Copy and Markdown content grouping | `frontend/src/features/transcript/collectionOutput.ts` |
| Actual-time active subtitle lookup | `frontend/src/features/transcript/findActiveSegmentIndex.ts` |
| Library query invalidation and intent keys | `frontend/src/features/collections/shared.ts` |
| Canonical favorite reuse | `backend/app/services/transcript_marks.py` |
| Source parsing/reconstruction vs DB publication | `backend/app/services/transcript/source_learning.py` vs `backend/app/services/source_learning.py` |
| ORM/session/configuration conventions | [backend guidelines](../backend/index.md) |

These are examples, not a requirement to put unrelated logic into the same module. Reuse a helper when semantics and future changes belong together; equal literals alone do not establish shared ownership. Keep a feature-local helper local when generalization would add coupling.

## Before Finishing

Search every consumer of changed types, configuration names, error codes and query keys. Verify related API schemas/client types and relevant tests, rather than relying on a global replace. After a source/algorithm change, read [source identity](../contracts/source-exchange.md) and [publication identity](../contracts/publication.md) before assuming old external results are reusable.

Current rules have one spec authority; tasks link to it. Historical documentation and generated tool code are not alternative implementation paths to revive. Project work does not require synchronizing Trellis upstream template directories or editing the globally installed package.
