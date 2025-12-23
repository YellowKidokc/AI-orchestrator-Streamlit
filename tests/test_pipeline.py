"""Tests for the pipeline execution framework."""

import pytest
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.step import Step, StepResult
from core.context import ExecutionContext
from core.pipeline import Pipeline, PipelineConfig
from core.step_factory import StepFactory, register_step


class TestExecutionContext:
    """Tests for ExecutionContext."""

    def test_basic_operations(self):
        """Test get/set operations on context."""
        ctx = ExecutionContext(pipeline_name="test")
        ctx.set("key1", "value1")
        assert ctx.get("key1") == "value1"
        assert ctx.get("missing", "default") == "default"

    def test_variable_interpolation(self):
        """Test variable interpolation in strings."""
        ctx = ExecutionContext(
            pipeline_name="test",
            variables={"city": "Chicago", "year": 2023}
        )
        result = ctx.interpolate("Data for ${city} in ${year}")
        assert result == "Data for Chicago in 2023"

    def test_nested_interpolation(self):
        """Test interpolation in nested structures."""
        ctx = ExecutionContext(
            pipeline_name="test",
            variables={"name": "test"}
        )
        result = ctx.interpolate({
            "key": "${name}",
            "nested": {"inner": "${name}"}
        })
        assert result == {"key": "test", "nested": {"inner": "test"}}

    def test_logging(self):
        """Test execution logging."""
        ctx = ExecutionContext(pipeline_name="test")
        ctx.log_start("step1")
        ctx.log_complete(success=True)
        assert len(ctx.logs) == 1
        assert ctx.logs[0].step_name == "step1"
        assert ctx.logs[0].success is True

    def test_checkpoint(self):
        """Test checkpoint save/restore."""
        ctx = ExecutionContext(pipeline_name="test")
        ctx.set("value", 1)
        ctx.checkpoint("before")
        ctx.set("value", 2)
        assert ctx.get("value") == 2
        ctx.restore_checkpoint("before")
        assert ctx.get("value") == 1

    def test_to_dict(self):
        """Test serialization to dict."""
        ctx = ExecutionContext(pipeline_name="test", variables={"x": 1})
        ctx.set("data", [1, 2, 3])
        result = ctx.to_dict()
        assert result["pipeline_name"] == "test"
        assert result["variables"] == {"x": 1}
        assert result["data"]["data"] == [1, 2, 3]


class TestStep:
    """Tests for Step base class."""

    def test_custom_step(self):
        """Test creating a custom step."""
        class AddStep(Step):
            name = "add"
            description = "Add two numbers"

            def run(self, context):
                a = self.config.get("a", 0)
                b = self.config.get("b", 0)
                context.set("result", a + b)
                return context

        step = AddStep({"a": 5, "b": 3})
        ctx = ExecutionContext(pipeline_name="test")
        result = step.run(ctx)
        assert result.get("result") == 8


class TestStepFactory:
    """Tests for StepFactory."""

    def test_register_and_create(self):
        """Test registering and creating steps."""
        @register_step("test_step")
        class TestStep(Step):
            name = "test_step"
            description = "A test step"

            def run(self, context):
                context.set("ran", True)
                return context

        factory = StepFactory()
        step = factory.create({"type": "test_step"})
        assert step.name == "test_step"

        ctx = ExecutionContext(pipeline_name="test")
        result = step.run(ctx)
        assert result.get("ran") is True

    def test_unknown_type_raises(self):
        """Test that unknown step types raise ValueError."""
        factory = StepFactory()
        with pytest.raises(ValueError, match="Unknown step type"):
            factory.create({"type": "nonexistent_step"})

    def test_list_types(self):
        """Test listing available step types."""
        factory = StepFactory()
        types = factory.list_types()
        assert isinstance(types, dict)


class TestPipeline:
    """Tests for Pipeline execution."""

    def test_simple_pipeline(self):
        """Test executing a simple pipeline."""
        class IncrementStep(Step):
            name = "increment"
            description = "Increment a counter"

            def run(self, context):
                val = context.get("counter", 0)
                context.set("counter", val + 1)
                return context

        pipeline = Pipeline(
            steps=[IncrementStep(), IncrementStep(), IncrementStep()],
            name="test_pipeline"
        )

        result = pipeline.run(initial_data={"counter": 0})
        assert result.success is True
        assert result.context.get("counter") == 3

    def test_pipeline_with_variables(self):
        """Test pipeline with variable interpolation."""
        class SetValueStep(Step):
            name = "set_value"
            description = "Set a value from config"

            def run(self, context):
                key = context.interpolate(self.config.get("key", ""))
                value = context.interpolate(self.config.get("value", ""))
                context.set(key, value)
                return context

        pipeline = Pipeline(
            steps=[SetValueStep({"key": "city", "value": "${location}"})],
            name="test_pipeline"
        )

        result = pipeline.run(variables={"location": "Chicago"})
        assert result.success is True
        assert result.context.get("city") == "Chicago"

    def test_pipeline_error_handling(self):
        """Test pipeline stops on error."""
        class FailingStep(Step):
            name = "failing"
            description = "Always fails"

            def run(self, context):
                raise RuntimeError("Intentional failure")

        class CounterStep(Step):
            name = "counter"
            description = "Count executions"

            def run(self, context):
                context.set("ran", True)
                return context

        pipeline = Pipeline(
            steps=[CounterStep(), FailingStep(), CounterStep()],
            name="test_pipeline"
        )

        result = pipeline.run()
        assert result.success is False
        assert result.failed_step == "failing"
        assert "Intentional failure" in result.error

    def test_continue_on_error(self):
        """Test pipeline continues on error when configured."""
        class FailingStep(Step):
            name = "failing"
            description = "Always fails"

            def run(self, context):
                raise RuntimeError("Intentional failure")

        class CounterStep(Step):
            name = "counter"
            description = "Count executions"

            def run(self, context):
                count = context.get("count", 0)
                context.set("count", count + 1)
                return context

        pipeline = Pipeline(
            steps=[CounterStep(), FailingStep(), CounterStep()],
            name="test_pipeline",
            continue_on_error=True
        )

        result = pipeline.run()
        # Should have run both counter steps despite failure
        assert result.context.get("count") == 2


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_from_dict(self):
        """Test creating config from dict."""
        config = PipelineConfig.from_dict({
            "name": "test",
            "description": "A test pipeline",
            "steps": [{"type": "api_fetch", "url": "http://example.com"}],
            "variables": {"limit": 10}
        })
        assert config.name == "test"
        assert len(config.steps) == 1
        assert config.variables["limit"] == 10

    def test_to_dict(self):
        """Test serializing config to dict."""
        config = PipelineConfig(
            name="test",
            description="Test",
            steps=[{"type": "test"}],
            variables={"x": 1}
        )
        result = config.to_dict()
        assert result["name"] == "test"
        assert result["steps"] == [{"type": "test"}]


class TestBuiltInSteps:
    """Tests for built-in step implementations."""

    def test_transform_step(self):
        """Test transform step extracts fields."""
        from steps.transform import TransformStep

        step = TransformStep({
            "input_key": "data",
            "output_key": "result",
            "extract": ["id", "name"]
        })

        ctx = ExecutionContext(pipeline_name="test")
        ctx.set("data", [
            {"id": 1, "name": "Alice", "extra": "ignored"},
            {"id": 2, "name": "Bob", "extra": "ignored"}
        ])

        result = step.run(ctx)
        assert result.get("result") == [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]

    def test_filter_step(self):
        """Test filter step filters data."""
        from steps.transform import FilterStep

        step = FilterStep({
            "input_key": "data",
            "output_key": "result",
            "conditions": [{"field": "value", "op": "gt", "value": 5}]
        })

        ctx = ExecutionContext(pipeline_name="test")
        ctx.set("data", [
            {"value": 3},
            {"value": 7},
            {"value": 10},
            {"value": 2}
        ])

        result = step.run(ctx)
        assert result.get("result") == [{"value": 7}, {"value": 10}]

    def test_aggregate_step(self):
        """Test aggregate step computes summaries."""
        from steps.transform import AggregateStep

        step = AggregateStep({
            "input_key": "data",
            "output_key": "stats",
            "operations": [
                {"field": "value", "func": "count", "alias": "total"},
                {"field": "value", "func": "sum", "alias": "sum"},
                {"field": "value", "func": "avg", "alias": "average"}
            ]
        })

        ctx = ExecutionContext(pipeline_name="test")
        ctx.set("data", [{"value": 10}, {"value": 20}, {"value": 30}])

        result = step.run(ctx)
        stats = result.get("stats")
        assert stats["total"] == 3
        assert stats["sum"] == 60
        assert stats["average"] == 20.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
