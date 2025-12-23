"""
Execution context for pipeline steps.

The context is the shared state passed between steps,
containing data, metadata, and execution history.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import copy


@dataclass
class ExecutionLog:
    """Log entry for a single step execution."""
    step_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def duration_ms(self) -> Optional[float]:
        """Get execution duration in milliseconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None


class ExecutionContext:
    """
    Shared context passed between pipeline steps.

    The context provides:
    - A data dictionary for passing values between steps
    - Execution metadata (pipeline name, timestamps)
    - Execution log for tracking step history
    - Variable interpolation for config values
    """

    def __init__(
        self,
        pipeline_name: str = "unnamed",
        variables: Optional[Dict[str, Any]] = None,
        initial_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize execution context.

        Args:
            pipeline_name: Name of the pipeline being executed
            variables: User-provided variables for interpolation
            initial_data: Initial data to populate context
        """
        self.pipeline_name = pipeline_name
        self.variables = variables or {}
        self.data: Dict[str, Any] = initial_data or {}
        self.metadata: Dict[str, Any] = {
            "pipeline_name": pipeline_name,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }
        self._logs: List[ExecutionLog] = []
        self._checkpoints: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the data dictionary."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the data dictionary."""
        self.data[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        """Update multiple values in the data dictionary."""
        self.data.update(values)

    def interpolate(self, value: Any) -> Any:
        """
        Interpolate variables in a value.

        Supports string interpolation with ${var_name} syntax.
        Recursively processes dictionaries and lists.

        Args:
            value: Value to interpolate

        Returns:
            Interpolated value
        """
        if isinstance(value, str):
            result = value
            for var_name, var_value in self.variables.items():
                result = result.replace(f"${{{var_name}}}", str(var_value))
            # Also interpolate from data
            for data_key, data_value in self.data.items():
                if isinstance(data_value, (str, int, float, bool)):
                    result = result.replace(f"${{data.{data_key}}}", str(data_value))
            return result
        elif isinstance(value, dict):
            return {k: self.interpolate(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.interpolate(v) for v in value]
        return value

    def log_start(self, step_name: str) -> None:
        """Log the start of a step execution."""
        self._logs.append(ExecutionLog(
            step_name=step_name,
            started_at=datetime.utcnow(),
        ))

    def log_complete(self, success: bool = True, error: Optional[str] = None, **metadata) -> None:
        """Log the completion of the current step."""
        if self._logs:
            current = self._logs[-1]
            current.completed_at = datetime.utcnow()
            current.success = success
            current.error = error
            current.metadata.update(metadata)

    def checkpoint(self, name: str) -> None:
        """Save a checkpoint of current data state."""
        self._checkpoints[name] = copy.deepcopy(self.data)

    def restore_checkpoint(self, name: str) -> bool:
        """Restore data from a checkpoint."""
        if name in self._checkpoints:
            self.data = copy.deepcopy(self._checkpoints[name])
            return True
        return False

    @property
    def logs(self) -> List[ExecutionLog]:
        """Get execution logs."""
        return self._logs

    @property
    def last_error(self) -> Optional[str]:
        """Get the last error from logs, if any."""
        for log in reversed(self._logs):
            if log.error:
                return log.error
        return None

    def finalize(self) -> None:
        """Mark the context as finalized."""
        self.metadata["completed_at"] = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for serialization."""
        return {
            "pipeline_name": self.pipeline_name,
            "variables": self.variables,
            "data": self.data,
            "metadata": self.metadata,
            "logs": [
                {
                    "step_name": log.step_name,
                    "started_at": log.started_at.isoformat(),
                    "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                    "success": log.success,
                    "error": log.error,
                    "duration_ms": log.duration_ms(),
                    "metadata": log.metadata,
                }
                for log in self._logs
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert context to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionContext":
        """Create context from dictionary."""
        ctx = cls(
            pipeline_name=data.get("pipeline_name", "unnamed"),
            variables=data.get("variables", {}),
            initial_data=data.get("data", {}),
        )
        ctx.metadata = data.get("metadata", ctx.metadata)
        return ctx

    def __repr__(self) -> str:
        return f"ExecutionContext(pipeline={self.pipeline_name}, keys={list(self.data.keys())})"
