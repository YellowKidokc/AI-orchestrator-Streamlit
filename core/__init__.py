"""
Core pipeline execution framework.

This module provides the fundamental abstractions for building
config-driven, step-based pipelines with a thin GUI layer.
"""

from core.step import Step
from core.context import ExecutionContext
from core.pipeline import Pipeline
from core.step_factory import StepFactory, register_step

__all__ = [
    "Step",
    "ExecutionContext",
    "Pipeline",
    "StepFactory",
    "register_step",
]
