"""
Pipeline engine for executing step sequences.

The pipeline orchestrates execution, handles errors,
and maintains execution state.
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
import yaml
import json
from pathlib import Path

from core.step import Step, StepResult
from core.context import ExecutionContext


@dataclass
class PipelineConfig:
    """Configuration for a pipeline."""
    name: str
    description: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> "PipelineConfig":
        """Load pipeline configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(
            name=data.get("name", Path(path).stem),
            description=data.get("description", ""),
            steps=data.get("steps", []),
            variables=data.get("variables", {}),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        """Create configuration from dictionary."""
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            steps=data.get("steps", []),
            variables=data.get("variables", {}),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "variables": self.variables,
            "metadata": self.metadata,
        }

    def to_yaml(self, path: str) -> None:
        """Save configuration to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""
    success: bool
    context: ExecutionContext
    failed_step: Optional[str] = None
    error: Optional[str] = None


class Pipeline:
    """
    Pipeline engine that executes a sequence of steps.

    Features:
    - Sequential step execution
    - Error handling with optional continuation
    - Execution logging and metrics
    - Dry-run capability
    - Config-driven or programmatic step definition
    """

    def __init__(
        self,
        steps: Optional[List[Step]] = None,
        name: str = "unnamed",
        description: str = "",
        on_step_start: Optional[Callable[[Step, ExecutionContext], None]] = None,
        on_step_complete: Optional[Callable[[Step, ExecutionContext, bool], None]] = None,
        continue_on_error: bool = False,
    ):
        """
        Initialize pipeline.

        Args:
            steps: List of steps to execute
            name: Pipeline name for identification
            description: Human-readable description
            on_step_start: Callback when a step starts
            on_step_complete: Callback when a step completes
            continue_on_error: Whether to continue after step failure
        """
        self.steps = steps or []
        self.name = name
        self.description = description
        self.on_step_start = on_step_start
        self.on_step_complete = on_step_complete
        self.continue_on_error = continue_on_error

    def add_step(self, step: Step) -> "Pipeline":
        """Add a step to the pipeline (fluent interface)."""
        self.steps.append(step)
        return self

    def run(
        self,
        variables: Optional[Dict[str, Any]] = None,
        initial_data: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """
        Execute the pipeline.

        Args:
            variables: Variables for interpolation in step configs
            initial_data: Initial data to populate context

        Returns:
            PipelineResult with success status and final context
        """
        context = ExecutionContext(
            pipeline_name=self.name,
            variables=variables or {},
            initial_data=initial_data or {},
        )

        for step in self.steps:
            context.log_start(step.name)

            if self.on_step_start:
                self.on_step_start(step, context)

            try:
                context = step.run(context)
                context.log_complete(success=True)

                if self.on_step_complete:
                    self.on_step_complete(step, context, True)

            except Exception as e:
                error_msg = str(e)
                context.log_complete(success=False, error=error_msg)

                if self.on_step_complete:
                    self.on_step_complete(step, context, False)

                if not self.continue_on_error:
                    context.finalize()
                    return PipelineResult(
                        success=False,
                        context=context,
                        failed_step=step.name,
                        error=error_msg,
                    )

        context.finalize()
        return PipelineResult(success=True, context=context)

    def dry_run(
        self,
        variables: Optional[Dict[str, Any]] = None,
    ) -> List[StepResult]:
        """
        Preview pipeline execution without running.

        Args:
            variables: Variables for interpolation

        Returns:
            List of StepResult previews
        """
        context = ExecutionContext(
            pipeline_name=self.name,
            variables=variables or {},
        )

        results = []
        for step in self.steps:
            result = step.dry_run(context)
            results.append(result)

        return results

    @classmethod
    def from_config(
        cls,
        config: PipelineConfig,
        step_factory: "StepFactory",
    ) -> "Pipeline":
        """
        Create pipeline from configuration.

        Args:
            config: Pipeline configuration
            step_factory: Factory for creating steps from config

        Returns:
            Configured Pipeline instance
        """
        steps = [step_factory.create(step_config) for step_config in config.steps]
        return cls(
            steps=steps,
            name=config.name,
            description=config.description,
        )

    def __repr__(self) -> str:
        return f"Pipeline(name={self.name}, steps={len(self.steps)})"


# Import here to avoid circular import
from core.step_factory import StepFactory
