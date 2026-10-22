# Frontend Engineering Guidelines

Status: source-backed engineering baseline, 2026-10-21. Current product semantics live in [product specs](../product/index.md); detailed contracts live in [current contracts](../contracts/index.md).

## Pre-Development Checklist

1. Read [shared engineering rules](../guides/project-engineering.md).
2. Read [directory boundaries](directory-structure.md) before adding or moving modules.
3. For UI/state work read [components](component-guidelines.md), [state management](state-management.md) and [hooks](hook-guidelines.md).
4. For API/type changes read [type safety](type-safety.md) and the corresponding backend schema and effective contract.
5. Read [quality checks](quality-guidelines.md) before selecting verification.

## Quality Check

Check browser-resource cleanup, query identity/invalidation, visible errors and the relevant behavior tests. Build includes TypeScript checking; there is no configured lint script. Preserve the distinction between mocked player tests and real YouTube acceptance.
