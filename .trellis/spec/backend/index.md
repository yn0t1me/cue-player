# Backend Engineering Guidelines

Status: source-backed engineering baseline, 2026-10-21. Current product semantics live in [product specs](../product/index.md); detailed technical contracts live in [current contracts](../contracts/index.md).

## Pre-Development Checklist

1. Read [shared engineering rules](../guides/project-engineering.md).
2. Read [directory and runtime boundaries](directory-structure.md) for backend work.
3. Read [database rules](database-guidelines.md) for persistence, lifecycle or migrations.
4. Read [errors](error-handling.md) and [logging](logging-guidelines.md) when touching failure paths.
5. Select verification from [quality guidelines](quality-guidelines.md).

## Quality Check

Verify transaction ownership, external work outside write transactions, session/resource cleanup and error response shape. Use isolated databases for migration/tests; disclose whether external services and real playback were exercised.
