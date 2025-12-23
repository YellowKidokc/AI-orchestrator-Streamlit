"""
Abstract Step interface.

Every reusable action implements this interface, enabling:
- Swappable components
- Consistent execution model
- Easy testing and composition
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class StepResult:
    """Result of a step execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Step(ABC):
    """
    Abstract base class for all pipeline steps.

    Each step:
    - Receives a shared context dictionary
    - Performs a single, focused operation
    - Returns the modified context
    - Can optionally validate its configuration
    """

    name: str = "base_step"
    description: str = "Base step"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize step with optional configuration.

        Args:
            config: Step-specific configuration dictionary
        """
        self.config = config or {}
        self._validate_config()

    def _validate_config(self) -> None:
        """
        Validate step configuration.
        Override in subclasses for custom validation.
        Raises ValueError if configuration is invalid.
        """
        pass

    @abstractmethod
    def run(self, context: "ExecutionContext") -> "ExecutionContext":
        """
        Execute the step.

        Args:
            context: Shared execution context

        Returns:
            Modified execution context
        """
        pass

    def dry_run(self, context: "ExecutionContext") -> StepResult:
        """
        Preview what this step would do without executing.

        Args:
            context: Shared execution context

        Returns:
            StepResult with preview information
        """
        return StepResult(
            success=True,
            data=None,
            metadata={
                "step": self.name,
                "config": self.config,
                "description": self.description,
            }
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(config={self.config})"
