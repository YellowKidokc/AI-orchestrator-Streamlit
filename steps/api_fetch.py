"""
API Fetch step for making HTTP requests.

This step is reusable for any API:
- Crime stats
- Weather data
- Financial APIs
- Internal services
"""

from typing import Any, Dict, List, Optional
import json

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from core.step import Step
from core.context import ExecutionContext
from core.step_factory import register_step


@register_step("api_fetch")
class APIFetchStep(Step):
    """
    Generic API fetch step.

    Supports:
    - GET, POST, PUT, DELETE methods
    - Query parameters and headers
    - JSON request bodies
    - Response parsing
    - Variable interpolation
    """

    name = "api_fetch"
    description = "Fetch data from an HTTP API endpoint"

    config_schema = {
        "url": {"type": "string", "required": True, "description": "API endpoint URL"},
        "method": {"type": "string", "default": "GET", "description": "HTTP method"},
        "params": {"type": "object", "description": "Query parameters"},
        "headers": {"type": "object", "description": "HTTP headers"},
        "body": {"type": "object", "description": "JSON request body"},
        "output_key": {"type": "string", "default": "data", "description": "Key to store response in context"},
        "timeout": {"type": "number", "default": 30, "description": "Request timeout in seconds"},
    }

    def _validate_config(self) -> None:
        if not self.config.get("url"):
            raise ValueError("APIFetchStep requires 'url' in config")

    def run(self, context: ExecutionContext) -> ExecutionContext:
        if not HAS_REQUESTS:
            raise RuntimeError("requests library not installed. Run: pip install requests")

        # Interpolate config values
        url = context.interpolate(self.config["url"])
        method = self.config.get("method", "GET").upper()
        params = context.interpolate(self.config.get("params", {}))
        headers = context.interpolate(self.config.get("headers", {}))
        body = context.interpolate(self.config.get("body"))
        output_key = self.config.get("output_key", "data")
        timeout = self.config.get("timeout", 30)

        # Make request
        request_kwargs = {
            "method": method,
            "url": url,
            "params": params if params else None,
            "headers": headers if headers else None,
            "timeout": timeout,
        }

        if body and method in ("POST", "PUT", "PATCH"):
            request_kwargs["json"] = body

        response = requests.request(**request_kwargs)
        response.raise_for_status()

        # Parse response
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
        else:
            data = response.text

        # Store in context
        context.set(output_key, data)
        context.set(f"{output_key}_status", response.status_code)
        context.set(f"{output_key}_headers", dict(response.headers))

        return context

    def dry_run(self, context: ExecutionContext) -> "StepResult":
        from core.step import StepResult
        url = context.interpolate(self.config.get("url", ""))
        return StepResult(
            success=True,
            metadata={
                "step": self.name,
                "action": f"{self.config.get('method', 'GET')} {url}",
                "output_key": self.config.get("output_key", "data"),
            }
        )


@register_step("api_fetch_paginated")
class PaginatedAPIFetchStep(Step):
    """
    Paginated API fetch that handles pagination automatically.

    Supports common pagination patterns:
    - offset/limit
    - page number
    - cursor-based
    """

    name = "api_fetch_paginated"
    description = "Fetch paginated data from an API endpoint"

    config_schema = {
        "url": {"type": "string", "required": True},
        "pagination_type": {"type": "string", "enum": ["offset", "page", "cursor"], "default": "offset"},
        "page_param": {"type": "string", "default": "page"},
        "limit_param": {"type": "string", "default": "limit"},
        "limit": {"type": "number", "default": 100},
        "max_pages": {"type": "number", "default": 10},
        "data_path": {"type": "string", "description": "JSON path to data array in response"},
        "next_cursor_path": {"type": "string", "description": "JSON path to next cursor"},
        "output_key": {"type": "string", "default": "data"},
    }

    def _validate_config(self) -> None:
        if not self.config.get("url"):
            raise ValueError("PaginatedAPIFetchStep requires 'url' in config")

    def _extract_path(self, data: Any, path: str) -> Any:
        """Extract value from nested dict using dot notation."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                return None
        return current

    def run(self, context: ExecutionContext) -> ExecutionContext:
        if not HAS_REQUESTS:
            raise RuntimeError("requests library not installed")

        url = context.interpolate(self.config["url"])
        pagination_type = self.config.get("pagination_type", "offset")
        page_param = self.config.get("page_param", "page")
        limit_param = self.config.get("limit_param", "limit")
        limit = self.config.get("limit", 100)
        max_pages = self.config.get("max_pages", 10)
        data_path = self.config.get("data_path")
        next_cursor_path = self.config.get("next_cursor_path")
        output_key = self.config.get("output_key", "data")
        headers = context.interpolate(self.config.get("headers", {}))

        all_data: List[Any] = []
        page = 0
        offset = 0
        cursor = None

        for _ in range(max_pages):
            params = dict(context.interpolate(self.config.get("params", {})))

            if pagination_type == "page":
                params[page_param] = page
                params[limit_param] = limit
            elif pagination_type == "offset":
                params["offset"] = offset
                params[limit_param] = limit
            elif pagination_type == "cursor" and cursor:
                params["cursor"] = cursor

            response = requests.get(url, params=params, headers=headers or None, timeout=30)
            response.raise_for_status()
            result = response.json()

            # Extract data
            if data_path:
                page_data = self._extract_path(result, data_path)
            else:
                page_data = result

            if isinstance(page_data, list):
                all_data.extend(page_data)
                if len(page_data) < limit:
                    break
            else:
                all_data.append(page_data)
                break

            # Handle pagination
            if pagination_type == "cursor":
                cursor = self._extract_path(result, next_cursor_path) if next_cursor_path else None
                if not cursor:
                    break
            elif pagination_type == "page":
                page += 1
            else:
                offset += limit

        context.set(output_key, all_data)
        context.set(f"{output_key}_count", len(all_data))

        return context


# Import StepResult for type hints
from core.step import StepResult
