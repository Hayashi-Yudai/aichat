from typing import Any

from loguru import logger
from mcp import Tool
from google.genai import types


class OpenAIToolFormatter:
    @classmethod
    def format(cls, tools: list[Tool]) -> list[dict[str, Any]]:
        logger.info("Formatting tools for OpenAI...")
        formatted_tools = []
        for tool in tools:
            # Ensure parameters schema is valid for OpenAI (requires properties)
            params = tool.inputSchema or {"type": "object", "properties": {}}
            if (
                isinstance(params, dict)
                and params.get("type") == "object"
                and "properties" not in params
            ):
                logger.warning(
                    f"Tool '{tool.name}' has no properties in schema for OpenAI. Adding empty properties."
                )
                params["properties"] = {}  # Add empty properties if missing

            formatted_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": params,
                    },
                }
            )
        return formatted_tools


class GeminiToolFormatter:
    @classmethod
    def format(cls, tools: list[Tool]) -> list[dict[str, Any]]:
        def format_schema(s: dict) -> dict:
            # Recursively format for 'Schema' class
            if s.get("items"):
                s["items"] = format_schema(s["items"])
            if s.get("properties"):
                s["properties"] = {
                    k: format_schema(v) for k, v in s["properties"].items()
                }

            # Gemini does not support these properties
            if s.get("additionalProperties") is not None:
                s.pop("additionalProperties")
            if s.get("$schema") is not None:
                s.pop("$schema")
            if s.get("default") is not None:
                s.pop("default")

            return s

        logger.info("Formatting tools for Gemini...")
        formatted_tools = []
        for tool in tools:
            tools_dict = {
                "name": tool.name,
                "description": tool.description,
            }
            parameters = {
                "type": tool.inputSchema["type"],
                "required": tool.inputSchema.get("required", []),
                "properties": tool.inputSchema.get("properties", {}),
            }

            for k, v in parameters["properties"].items():
                parameters["properties"][k] = format_schema(v)

            tools_dict["parameters"] = parameters
            formatted_tools.append(types.Tool(function_declarations=[tools_dict]))

        return formatted_tools


class ClaudeToolFormatter:
    @classmethod
    def format(cls, tools: list[Tool]) -> list[dict[str, Any]]:
        logger.info("Formatting tools for Claude...")
        formatted_tools = []
        for tool in tools:
            # Ensure input_schema is valid (add empty properties if needed for consistency)
            input_schema = tool.inputSchema or {"type": "object", "properties": {}}
            if (
                isinstance(input_schema, dict)
                and input_schema.get("type") == "object"
                and "properties" not in input_schema
            ):
                logger.warning(
                    f"Tool '{tool.name}' schema for Claude lacks properties. "
                    "Adding empty properties for consistency."
                )
                input_schema["properties"] = {}  # Add empty properties if missing

            formatted_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": input_schema,  # Use potentially modified input_schema
                }
            )
        return formatted_tools
