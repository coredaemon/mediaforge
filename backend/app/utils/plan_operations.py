from __future__ import annotations

from collections.abc import Iterable

from ..models.plan_operation import PlanOperation


def dedupe_operations(operations: Iterable[PlanOperation]) -> list[PlanOperation]:
    """Drop operations that repeat an earlier one verbatim, keeping order.

    Planning legitimately produces the same operation more than once -- one
    CREATE_DIR per episode for a shared season folder, one poster download per
    episode for a shared show folder. Re-running them is redundant at best and,
    for downloads and NFO writes, fails outright on the second attempt because
    the target now exists. Operations that differ in source are left alone:
    those are real collisions and validation must surface them.
    """
    seen: set[tuple[str, str | None, str | None]] = set()
    unique: list[PlanOperation] = []
    for operation in operations:
        signature = (
            operation.operation_type.value,
            operation.source_path,
            operation.target_path,
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(operation)
    return unique
