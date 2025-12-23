"""
Step factory for creating steps from configuration.

This enables config-driven pipelines where steps are
defined in YAML/JSON and instantiated at runtime.
"""

from typing import Any, Callable, Dict, Optional, Type
from core.step import Step

# Global registry of step types
_STEP_REGISTRY: Dict[str, Type[Step]] = {}


def register_step(name: str) -> Callable[[Type[Step]], Type[Step]]:
    """
    Decorator to register a step class.

    Usage:
        @register_step("api_fetch")
        class APIFetchStep(Step):
            ...

    Args:
        name: The type name used in config files

    Returns:
        Decorator function
    """
    def decorator(cls: Type[Step]) -> Type[Step]:
        _STEP_REGISTRY[name] = cls
        cls.name = name
        return cls
    return decorator


class StepFactory:
    """
    Factory for creating step instances from configuration.

    Maps step type names to step classes and instantiates
    them with the provided configuration.
    """

    def __init__(self, additional_registry: Optional[Dict[str, Type[Step]]] = None):
        """
        Initialize factory.

        Args:
            additional_registry: Additional step types to register
        """
        self._registry = dict(_STEP_REGISTRY)
        if additional_registry:
            self._registry.update(additional_registry)

    def register(self, name: str, step_class: Type[Step]) -> None:
        """
        Register a step type.

        Args:
            name: Type name for config files
            step_class: Step class to instantiate
        """
        self._registry[name] = step_class

    def create(self, step_config: Dict[str, Any]) -> Step:
        """
        Create a step from configuration.

        Args:
            step_config: Step configuration with 'type' key

        Returns:
            Instantiated Step

        Raises:
            ValueError: If step type is unknown
        """
        step_type = step_config.get("type")
        if not step_type:
            raise ValueError("Step config must include 'type' key")

        if step_type not in self._registry:
            available = ", ".join(sorted(self._registry.keys()))
            raise ValueError(
                f"Unknown step type: {step_type}. Available types: {available}"
            )

        step_class = self._registry[step_type]
        config = {k: v for k, v in step_config.items() if k != "type"}

        return step_class(config)

    def list_types(self) -> Dict[str, str]:
        """
        List available step types with descriptions.

        Returns:
            Dictionary of type name -> description
        """
        return {
            name: cls.description
            for name, cls in sorted(self._registry.items())
        }

    def get_schema(self, step_type: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration schema for a step type.

        Args:
            step_type: The step type name

        Returns:
            Schema dictionary or None if not found
        """
        if step_type not in self._registry:
            return None

        cls = self._registry[step_type]
        if hasattr(cls, "config_schema"):
            return cls.config_schema
        return None


# Create default factory instance
default_factory = StepFactory()
