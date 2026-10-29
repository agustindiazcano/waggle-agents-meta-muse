"""Per-task call and cost caps."""

from dataclasses import dataclass, field

from waggle.llm.errors import TaskCapExceededError


@dataclass(frozen=True)
class TaskCaps:
    """Maximum calls and cost for one task."""

    max_calls: int
    max_cost_usd: float


@dataclass
class TaskLedger:
    """Tracks calls and cost per task id."""

    caps: TaskCaps
    calls: dict[str, int] = field(default_factory=dict)
    cost: dict[str, float] = field(default_factory=dict)

    def check(self, task_id: str, estimate: float) -> None:
        """Raise TaskCapExceededError if one more call would pass a cap."""
        if self.calls.get(task_id, 0) + 1 > self.caps.max_calls:
            raise TaskCapExceededError(f"task {task_id}: call cap {self.caps.max_calls} reached")
        if self.cost.get(task_id, 0.0) + estimate > self.caps.max_cost_usd:
            raise TaskCapExceededError(f"task {task_id}: cost cap {self.caps.max_cost_usd} reached")

    def record(self, task_id: str, cost: float) -> None:
        """Count one finished call."""
        self.calls[task_id] = self.calls.get(task_id, 0) + 1
        self.cost[task_id] = self.cost.get(task_id, 0.0) + cost
