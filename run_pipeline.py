#!/usr/bin/env python3
"""
CLI runner for executing pipelines.

Usage:
    python run_pipeline.py <config_path> [--var key=value ...]
    python run_pipeline.py --list
    python run_pipeline.py --dry-run <config_path>

Examples:
    python run_pipeline.py config/pipelines/example_api.yaml
    python run_pipeline.py config/pipelines/vault_search.yaml --var query=ethics
    python run_pipeline.py --list
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.pipeline import Pipeline, PipelineConfig
from core.step_factory import StepFactory

# Import steps to register them
import steps  # noqa: F401


def list_pipelines(config_dir: str = "config/pipelines") -> None:
    """List available pipeline configurations."""
    config_path = Path(config_dir)
    if not config_path.exists():
        print(f"No pipelines directory found at: {config_dir}")
        return

    pipelines = list(config_path.glob("*.yaml")) + list(config_path.glob("*.yml"))

    if not pipelines:
        print(f"No pipeline configs found in: {config_dir}")
        return

    print("\nAvailable Pipelines:")
    print("-" * 60)

    for p in sorted(pipelines):
        try:
            config = PipelineConfig.from_yaml(str(p))
            print(f"\n  {p.stem}")
            print(f"    File: {p}")
            print(f"    Description: {config.description or 'No description'}")
            print(f"    Steps: {len(config.steps)}")
            if config.variables:
                vars_str = ", ".join(f"{k}={v}" for k, v in config.variables.items())
                print(f"    Variables: {vars_str}")
        except Exception as e:
            print(f"\n  {p.stem} (error loading: {e})")

    print()


def list_step_types() -> None:
    """List available step types."""
    factory = StepFactory()
    types = factory.list_types()

    print("\nAvailable Step Types:")
    print("-" * 60)

    for name, desc in sorted(types.items()):
        print(f"  {name}: {desc}")

    print()


def parse_variables(var_args: list) -> Dict[str, Any]:
    """Parse --var key=value arguments."""
    variables = {}
    for var in var_args:
        if "=" in var:
            key, value = var.split("=", 1)
            # Try to parse as JSON for complex values
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass  # Keep as string
            variables[key] = value
    return variables


def run_pipeline_cli(
    config_path: str,
    variables: Dict[str, Any],
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Run a pipeline from CLI."""

    # Load configuration
    config = PipelineConfig.from_yaml(config_path)

    # Merge variables (CLI overrides config defaults)
    merged_vars = {**config.variables, **variables}

    # Create factory and pipeline
    factory = StepFactory()

    def on_step_start(step, context):
        if verbose:
            print(f"  → Starting: {step.name}")

    def on_step_complete(step, context, success):
        status = "✓" if success else "✗"
        if verbose or not success:
            print(f"  {status} Completed: {step.name}")
            if not success and context.last_error:
                print(f"    Error: {context.last_error}")

    pipeline = Pipeline.from_config(config, factory)
    pipeline.on_step_start = on_step_start
    pipeline.on_step_complete = on_step_complete

    print(f"\nPipeline: {config.name}")
    print(f"Description: {config.description}")
    print(f"Steps: {len(config.steps)}")

    if merged_vars:
        print(f"Variables: {json.dumps(merged_vars)}")

    print("-" * 60)

    if dry_run:
        print("\n[DRY RUN - No changes will be made]\n")
        results = pipeline.dry_run(variables=merged_vars)
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result.metadata.get('step', 'unknown')}")
            if "action" in result.metadata:
                print(f"     Action: {result.metadata['action']}")
        return 0

    # Execute pipeline
    print("\nExecuting...\n")
    result = pipeline.run(variables=merged_vars)

    print("-" * 60)

    if result.success:
        print("\n✓ Pipeline completed successfully")

        # Show execution summary
        if verbose:
            print("\nExecution Log:")
            for log in result.context.logs:
                duration = f" ({log.duration_ms():.0f}ms)" if log.duration_ms() else ""
                status = "✓" if log.success else "✗"
                print(f"  {status} {log.step_name}{duration}")

        # Show output data keys
        print(f"\nContext keys: {list(result.context.data.keys())}")

        return 0
    else:
        print(f"\n✗ Pipeline failed at step: {result.failed_step}")
        print(f"  Error: {result.error}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Run config-driven pipelines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "config",
        nargs="?",
        help="Path to pipeline config (YAML)",
    )
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override pipeline variable",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available pipelines",
    )
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="List available step types",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview pipeline without executing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--output-json",
        metavar="PATH",
        help="Write execution result to JSON file",
    )

    args = parser.parse_args()

    if args.list:
        list_pipelines()
        return 0

    if args.list_steps:
        list_step_types()
        return 0

    if not args.config:
        parser.print_help()
        print("\nError: config path required (or use --list)")
        return 1

    if not Path(args.config).exists():
        print(f"Error: Config file not found: {args.config}")
        return 1

    variables = parse_variables(args.var)

    result_code = run_pipeline_cli(
        args.config,
        variables,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    return result_code


if __name__ == "__main__":
    sys.exit(main())
