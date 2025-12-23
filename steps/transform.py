"""
Data transformation steps.

Generic, reusable transforms for:
- Filtering
- Mapping
- Aggregation
- Format conversion
"""

from typing import Any, Callable, Dict, List, Optional, Union
import json
import csv
import io

from core.step import Step, StepResult
from core.context import ExecutionContext
from core.step_factory import register_step


@register_step("transform")
class TransformStep(Step):
    """
    Generic data transformation step.

    Supports:
    - Field extraction
    - Renaming
    - Type conversion
    - Custom expressions
    """

    name = "transform"
    description = "Transform data by extracting, renaming, or converting fields"

    config_schema = {
        "input_key": {"type": "string", "default": "data", "description": "Context key containing input data"},
        "output_key": {"type": "string", "default": "data", "description": "Context key for output"},
        "extract": {"type": "array", "description": "Fields to extract from each item"},
        "rename": {"type": "object", "description": "Field rename mapping {old: new}"},
        "flatten": {"type": "boolean", "default": False, "description": "Flatten nested structures"},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        input_key = self.config.get("input_key", "data")
        output_key = self.config.get("output_key", "data")
        data = context.get(input_key)

        if data is None:
            raise ValueError(f"No data found at key: {input_key}")

        # Process based on data type
        if isinstance(data, list):
            result = [self._transform_item(item) for item in data]
        else:
            result = self._transform_item(data)

        context.set(output_key, result)
        return context

    def _transform_item(self, item: Any) -> Any:
        if not isinstance(item, dict):
            return item

        result = dict(item)

        # Extract specific fields
        extract = self.config.get("extract")
        if extract:
            result = {k: result.get(k) for k in extract if k in result}

        # Rename fields
        rename = self.config.get("rename", {})
        for old_name, new_name in rename.items():
            if old_name in result:
                result[new_name] = result.pop(old_name)

        # Flatten nested structures
        if self.config.get("flatten"):
            result = self._flatten_dict(result)

        return result

    def _flatten_dict(self, d: Dict, parent_key: str = "", sep: str = "_") -> Dict:
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            else:
                items.append((new_key, v))
        return dict(items)


@register_step("filter")
class FilterStep(Step):
    """
    Filter data based on conditions.

    Supports:
    - Field-based filtering
    - Comparison operators
    - Multiple conditions (AND/OR)
    """

    name = "filter"
    description = "Filter data based on field conditions"

    config_schema = {
        "input_key": {"type": "string", "default": "data"},
        "output_key": {"type": "string", "default": "data"},
        "conditions": {"type": "array", "required": True, "description": "List of filter conditions"},
        "match": {"type": "string", "enum": ["all", "any"], "default": "all"},
    }

    OPERATORS = {
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "in": lambda a, b: a in b,
        "not_in": lambda a, b: a not in b,
        "contains": lambda a, b: b in str(a),
        "startswith": lambda a, b: str(a).startswith(b),
        "endswith": lambda a, b: str(a).endswith(b),
        "exists": lambda a, b: a is not None if b else a is None,
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        input_key = self.config.get("input_key", "data")
        output_key = self.config.get("output_key", "data")
        conditions = self.config.get("conditions", [])
        match_mode = self.config.get("match", "all")

        data = context.get(input_key)
        if data is None:
            raise ValueError(f"No data found at key: {input_key}")

        if not isinstance(data, list):
            data = [data]

        # Interpolate condition values
        conditions = context.interpolate(conditions)

        result = [
            item for item in data
            if self._matches(item, conditions, match_mode)
        ]

        context.set(output_key, result)
        context.set(f"{output_key}_filtered_count", len(data) - len(result))
        return context

    def _matches(self, item: Any, conditions: List[Dict], match_mode: str) -> bool:
        if not isinstance(item, dict):
            return True

        results = []
        for cond in conditions:
            field = cond.get("field")
            op = cond.get("op", "eq")
            value = cond.get("value")

            item_value = self._get_nested(item, field)
            op_func = self.OPERATORS.get(op)

            if op_func:
                results.append(op_func(item_value, value))
            else:
                results.append(False)

        if match_mode == "any":
            return any(results)
        return all(results)

    def _get_nested(self, d: Dict, path: str) -> Any:
        """Get nested value using dot notation."""
        parts = path.split(".")
        current = d
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current


@register_step("map")
class MapStep(Step):
    """
    Map data through a transformation.

    Supports:
    - Expression-based mapping
    - Template strings
    - Computed fields
    """

    name = "map"
    description = "Map data through a transformation function"

    config_schema = {
        "input_key": {"type": "string", "default": "data"},
        "output_key": {"type": "string", "default": "data"},
        "template": {"type": "object", "description": "Template for each output item"},
        "add_fields": {"type": "object", "description": "Additional fields to add"},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        input_key = self.config.get("input_key", "data")
        output_key = self.config.get("output_key", "data")
        template = self.config.get("template")
        add_fields = self.config.get("add_fields", {})

        data = context.get(input_key)
        if data is None:
            raise ValueError(f"No data found at key: {input_key}")

        if not isinstance(data, list):
            data = [data]

        result = []
        for item in data:
            if template:
                mapped = self._apply_template(item, template)
            else:
                mapped = dict(item) if isinstance(item, dict) else {"value": item}

            # Add extra fields
            for field, value in add_fields.items():
                if isinstance(value, str) and value.startswith("$"):
                    mapped[field] = self._resolve_ref(item, value)
                else:
                    mapped[field] = context.interpolate(value)

            result.append(mapped)

        context.set(output_key, result)
        return context

    def _apply_template(self, item: Dict, template: Dict) -> Dict:
        """Apply template to item."""
        result = {}
        for key, value in template.items():
            if isinstance(value, str) and value.startswith("$."):
                result[key] = self._resolve_ref(item, value)
            elif isinstance(value, dict):
                result[key] = self._apply_template(item, value)
            else:
                result[key] = value
        return result

    def _resolve_ref(self, item: Dict, ref: str) -> Any:
        """Resolve a reference like $.field.subfield"""
        if not ref.startswith("$."):
            return ref
        path = ref[2:]
        parts = path.split(".")
        current = item
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current


@register_step("aggregate")
class AggregateStep(Step):
    """
    Aggregate data with grouping and summary functions.
    """

    name = "aggregate"
    description = "Aggregate data with grouping and summary operations"

    config_schema = {
        "input_key": {"type": "string", "default": "data"},
        "output_key": {"type": "string", "default": "data"},
        "group_by": {"type": "string", "description": "Field to group by"},
        "operations": {"type": "array", "description": "Aggregation operations"},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        input_key = self.config.get("input_key", "data")
        output_key = self.config.get("output_key", "data")
        group_by = self.config.get("group_by")
        operations = self.config.get("operations", [])

        data = context.get(input_key)
        if not isinstance(data, list):
            raise ValueError("Aggregate requires list data")

        if group_by:
            # Group data
            groups: Dict[Any, List] = {}
            for item in data:
                key = item.get(group_by) if isinstance(item, dict) else None
                if key not in groups:
                    groups[key] = []
                groups[key].append(item)

            # Aggregate each group
            result = []
            for group_key, group_items in groups.items():
                agg_result = {group_by: group_key}
                for op in operations:
                    field = op.get("field")
                    func = op.get("func", "count")
                    alias = op.get("alias", f"{func}_{field}")
                    agg_result[alias] = self._aggregate(group_items, field, func)
                result.append(agg_result)
        else:
            # Single aggregation
            result = {}
            for op in operations:
                field = op.get("field")
                func = op.get("func", "count")
                alias = op.get("alias", f"{func}_{field}")
                result[alias] = self._aggregate(data, field, func)

        context.set(output_key, result)
        return context

    def _aggregate(self, items: List, field: Optional[str], func: str) -> Any:
        if field:
            values = [
                item.get(field) for item in items
                if isinstance(item, dict) and item.get(field) is not None
            ]
        else:
            values = items

        if func == "count":
            return len(values)
        elif func == "sum":
            return sum(v for v in values if isinstance(v, (int, float)))
        elif func == "avg":
            nums = [v for v in values if isinstance(v, (int, float))]
            return sum(nums) / len(nums) if nums else 0
        elif func == "min":
            return min(values) if values else None
        elif func == "max":
            return max(values) if values else None
        elif func == "distinct":
            return list(set(values))
        elif func == "first":
            return values[0] if values else None
        elif func == "last":
            return values[-1] if values else None

        return None


@register_step("convert_format")
class ConvertFormatStep(Step):
    """
    Convert data between formats (JSON, CSV, etc.).
    """

    name = "convert_format"
    description = "Convert data between JSON, CSV, and other formats"

    config_schema = {
        "input_key": {"type": "string", "default": "data"},
        "output_key": {"type": "string", "default": "data"},
        "from_format": {"type": "string", "enum": ["json", "csv", "auto"], "default": "auto"},
        "to_format": {"type": "string", "enum": ["json", "csv", "dict"], "default": "dict"},
    }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        input_key = self.config.get("input_key", "data")
        output_key = self.config.get("output_key", "data")
        from_format = self.config.get("from_format", "auto")
        to_format = self.config.get("to_format", "dict")

        data = context.get(input_key)

        # Parse input
        if from_format == "csv" or (from_format == "auto" and isinstance(data, str) and "," in data):
            parsed = self._parse_csv(data)
        elif from_format == "json" or (from_format == "auto" and isinstance(data, str)):
            parsed = json.loads(data) if isinstance(data, str) else data
        else:
            parsed = data

        # Convert output
        if to_format == "csv":
            result = self._to_csv(parsed)
        elif to_format == "json":
            result = json.dumps(parsed, indent=2)
        else:
            result = parsed

        context.set(output_key, result)
        return context

    def _parse_csv(self, data: str) -> List[Dict]:
        reader = csv.DictReader(io.StringIO(data))
        return list(reader)

    def _to_csv(self, data: Union[List[Dict], Dict]) -> str:
        if not data:
            return ""

        if isinstance(data, dict):
            data = [data]

        output = io.StringIO()
        if data and isinstance(data[0], dict):
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return output.getvalue()
