import itertools
import sys  # Add sys import
from enum import StrEnum
from pathlib import Path

from .agent import Agent
from .mcp_handler import McpHandler  # Added McpHandler import
from .openai_agent import OpenAIAgent, OpenAIModel
from .gemini_agent import GeminiAgent, GeminiModel
from .deepseek_agent import DeepSeekAgent, DeepSeekModel
from .claude_agent import ClaudeAgent, ClaudeModel
from .local_agent import LocalAgent, LocalModel
from .mlx_model_agent import MLXAgent, MLXModel
from .dummy_agent import DummyAgent, DummyModel


# Base models available on all platforms
base_models = [
    OpenAIModel,
    GeminiModel,
    ClaudeModel,
    DeepSeekModel,
    LocalModel,
    DummyModel,
]

# Add MLXModel only if on macOS
if sys.platform == "darwin":
    base_models.append(MLXModel)

all_models = list(itertools.chain.from_iterable(base_models))


# Define the path to the MCP server script relative to this __init__.py
# This assumes a single, shared MCP handler instance for all agents needing it.
# If different agents need different handlers, this logic needs adjustment.
_mcp_handler_instance = McpHandler(Path(__file__).parent / "servers.json")


def get_agent_by_model(model: StrEnum) -> Agent:
    """Gets an agent instance based on the model enum."""
    # Pass the shared McpHandler instance to agents that need it
    if model in OpenAIModel:
        return OpenAIAgent(model, mcp_handler=_mcp_handler_instance)
    elif model in GeminiModel:
        return GeminiAgent(model, mcp_handler=_mcp_handler_instance)
    elif model in ClaudeModel:
        return ClaudeAgent(model, mcp_handler=_mcp_handler_instance)
    elif model in DeepSeekModel:
        # Assuming DeepSeekAgent does not use McpHandler (adjust if it does)
        return DeepSeekAgent(model)
    elif model in LocalModel:
        # Assuming LocalAgent does not use McpHandler (adjust if it does)
        return LocalAgent(model)
    elif model in MLXModel:
        return MLXAgent(model)
    elif model in DummyModel:
        return DummyAgent(model)
    else:
        raise ValueError(f"Invalid model: {model}")
