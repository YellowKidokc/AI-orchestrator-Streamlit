"""
Streamlit UI components for pipeline execution.

Provides a GUI layer for:
- Browsing available pipelines
- Configuring pipeline variables
- Executing pipelines
- Viewing results
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.pipeline import Pipeline, PipelineConfig, PipelineResult
from core.step_factory import StepFactory
from core.context import ExecutionContext

# Import steps to register them
import steps as _  # noqa: F401

PIPELINES_DIR = ROOT / "config" / "pipelines"


def load_pipeline_configs() -> Dict[str, PipelineConfig]:
    """Load all available pipeline configurations."""
    configs = {}
    if PIPELINES_DIR.exists():
        for path in PIPELINES_DIR.glob("*.yaml"):
            try:
                config = PipelineConfig.from_yaml(str(path))
                configs[path.stem] = config
            except Exception as e:
                st.warning(f"Failed to load {path.name}: {e}")
    return configs


def ensure_pipeline_state() -> None:
    """Initialize pipeline-related session state."""
    if "pipeline_configs" not in st.session_state:
        st.session_state.pipeline_configs = load_pipeline_configs()
    if "selected_pipeline" not in st.session_state:
        st.session_state.selected_pipeline = None
    if "pipeline_variables" not in st.session_state:
        st.session_state.pipeline_variables = {}
    if "pipeline_result" not in st.session_state:
        st.session_state.pipeline_result = None
    if "pipeline_logs" not in st.session_state:
        st.session_state.pipeline_logs = []


def render_pipeline_selector() -> Optional[PipelineConfig]:
    """Render pipeline selection dropdown."""
    configs = st.session_state.pipeline_configs

    if not configs:
        st.info("No pipeline configurations found. Add YAML files to config/pipelines/")
        return None

    options = ["Select a pipeline..."] + list(configs.keys())
    selected = st.selectbox(
        "Pipeline",
        options,
        index=0,
        format_func=lambda x: x if x == options[0] else f"{x} - {configs[x].description[:50]}..."
        if len(configs.get(x, PipelineConfig("")).description) > 50
        else x if x == options[0] else f"{x} - {configs[x].description}"
    )

    if selected == options[0]:
        return None

    st.session_state.selected_pipeline = selected
    return configs[selected]


def render_variable_inputs(config: PipelineConfig) -> Dict[str, Any]:
    """Render input fields for pipeline variables."""
    if not config.variables:
        return {}

    st.subheader("Variables")

    variables = {}
    for key, default_value in config.variables.items():
        # Determine input type based on default value type
        if isinstance(default_value, bool):
            variables[key] = st.checkbox(key, value=default_value)
        elif isinstance(default_value, int):
            variables[key] = st.number_input(key, value=default_value, step=1)
        elif isinstance(default_value, float):
            variables[key] = st.number_input(key, value=default_value)
        elif isinstance(default_value, list):
            # Multi-select or text input for lists
            as_text = st.text_input(key, value=json.dumps(default_value))
            try:
                variables[key] = json.loads(as_text)
            except json.JSONDecodeError:
                variables[key] = default_value
        else:
            variables[key] = st.text_input(key, value=str(default_value))

    return variables


def render_step_preview(config: PipelineConfig) -> None:
    """Show preview of pipeline steps."""
    with st.expander("Pipeline Steps", expanded=False):
        for i, step_config in enumerate(config.steps, 1):
            step_type = step_config.get("type", "unknown")
            step_info = {k: v for k, v in step_config.items() if k != "type"}
            st.markdown(f"**{i}. {step_type}**")
            if step_info:
                st.code(yaml.dump(step_info, default_flow_style=False), language="yaml")


def run_pipeline_with_ui(config: PipelineConfig, variables: Dict[str, Any]) -> PipelineResult:
    """Execute pipeline with progress UI."""
    factory = StepFactory()
    pipeline = Pipeline.from_config(config, factory)

    logs = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_steps = len(pipeline.steps)

    def on_step_start(step, context):
        step_num = len(context.logs)
        progress_bar.progress(step_num / total_steps)
        status_text.text(f"Running: {step.name}...")
        logs.append({"step": step.name, "status": "running"})

    def on_step_complete(step, context, success):
        status = "✓" if success else "✗"
        logs[-1]["status"] = status
        if not success and context.last_error:
            logs[-1]["error"] = context.last_error

    pipeline.on_step_start = on_step_start
    pipeline.on_step_complete = on_step_complete

    result = pipeline.run(variables=variables)

    progress_bar.progress(1.0)
    status_text.text("Complete!" if result.success else f"Failed at: {result.failed_step}")

    st.session_state.pipeline_logs = logs
    st.session_state.pipeline_result = result

    return result


def render_execution_results(result: PipelineResult) -> None:
    """Display pipeline execution results."""
    if result.success:
        st.success("Pipeline completed successfully!")
    else:
        st.error(f"Pipeline failed at step: {result.failed_step}")
        st.code(result.error)

    # Show execution log
    with st.expander("Execution Log", expanded=True):
        for log in result.context.logs:
            status = "✓" if log.success else "✗"
            duration = f" ({log.duration_ms():.0f}ms)" if log.duration_ms() else ""
            if log.success:
                st.markdown(f"{status} **{log.step_name}**{duration}")
            else:
                st.markdown(f"{status} **{log.step_name}**{duration}")
                if log.error:
                    st.code(log.error)

    # Show output data
    with st.expander("Output Data", expanded=False):
        for key, value in result.context.data.items():
            st.markdown(f"**{key}**")
            if isinstance(value, (dict, list)):
                st.json(value)
            else:
                st.code(str(value))


def render_pipeline_creator() -> None:
    """UI for creating new pipeline configurations."""
    st.subheader("Create New Pipeline")

    # Get available step types
    factory = StepFactory()
    step_types = factory.list_types()

    with st.form("new_pipeline"):
        name = st.text_input("Pipeline Name", placeholder="my_pipeline")
        description = st.text_area("Description", placeholder="What does this pipeline do?")

        st.markdown("**Steps**")
        st.caption("Define steps in YAML format")

        default_steps = """steps:
  - type: api_fetch
    url: "https://api.example.com/data"
    output_key: data

  - type: save_file
    input_key: data
    path: "data/output.json"
"""
        steps_yaml = st.text_area("Steps (YAML)", value=default_steps, height=200)

        st.markdown("**Variables**")
        variables_yaml = st.text_area(
            "Variables (YAML)",
            value="variables:\n  output_dir: data/output",
            height=100
        )

        submitted = st.form_submit_button("Create Pipeline")

        if submitted and name:
            try:
                steps_data = yaml.safe_load(steps_yaml)
                vars_data = yaml.safe_load(variables_yaml)

                config = PipelineConfig(
                    name=name,
                    description=description,
                    steps=steps_data.get("steps", []),
                    variables=vars_data.get("variables", {}),
                )

                # Save to file
                PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
                config.to_yaml(str(PIPELINES_DIR / f"{name}.yaml"))

                # Reload configs
                st.session_state.pipeline_configs = load_pipeline_configs()
                st.success(f"Created pipeline: {name}")

            except Exception as e:
                st.error(f"Failed to create pipeline: {e}")

    # Show available step types
    with st.expander("Available Step Types"):
        for type_name, type_desc in sorted(step_types.items()):
            st.markdown(f"- **{type_name}**: {type_desc}")


def render_pipeline_tab() -> None:
    """Main pipeline management tab."""
    ensure_pipeline_state()

    st.header("Pipeline Execution")
    st.caption("Run config-driven data pipelines with GUI controls")

    # Tabs for different pipeline actions
    tab_run, tab_create = st.tabs(["Run Pipeline", "Create Pipeline"])

    with tab_run:
        col1, col2 = st.columns([1, 1])

        with col1:
            # Pipeline selection
            config = render_pipeline_selector()

            if config:
                # Variable configuration
                variables = render_variable_inputs(config)

                # Step preview
                render_step_preview(config)

                # Run button
                st.markdown("---")
                col_run, col_dry = st.columns(2)

                with col_run:
                    if st.button("Run Pipeline", type="primary", use_container_width=True):
                        with st.spinner("Executing pipeline..."):
                            result = run_pipeline_with_ui(config, variables)

                with col_dry:
                    if st.button("Dry Run", use_container_width=True):
                        factory = StepFactory()
                        pipeline = Pipeline.from_config(config, factory)
                        preview = pipeline.dry_run(variables=variables)
                        st.info("Dry run preview:")
                        for i, step_result in enumerate(preview, 1):
                            st.markdown(f"{i}. {step_result.metadata.get('step', 'unknown')}")
                            if "action" in step_result.metadata:
                                st.caption(step_result.metadata["action"])

        with col2:
            # Results display
            if st.session_state.pipeline_result:
                render_execution_results(st.session_state.pipeline_result)
            else:
                st.info("Select and run a pipeline to see results here.")

    with tab_create:
        render_pipeline_creator()


def render_pipeline_sidebar_widget() -> None:
    """Compact pipeline widget for sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Quick Pipeline")

    configs = st.session_state.get("pipeline_configs", {})
    if not configs:
        configs = load_pipeline_configs()
        st.session_state.pipeline_configs = configs

    if not configs:
        st.sidebar.caption("No pipelines available")
        return

    selected = st.sidebar.selectbox(
        "Pipeline",
        options=list(configs.keys()),
        key="sidebar_pipeline_select",
    )

    if selected and st.sidebar.button("Run", key="sidebar_pipeline_run"):
        config = configs[selected]
        with st.spinner(f"Running {selected}..."):
            factory = StepFactory()
            pipeline = Pipeline.from_config(config, factory)
            result = pipeline.run(variables=config.variables)
            if result.success:
                st.sidebar.success("Pipeline completed!")
            else:
                st.sidebar.error(f"Failed: {result.error}")
