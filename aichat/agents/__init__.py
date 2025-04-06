from enum import StrEnum

from .openai_agent import OpenAIAgent, OpenAIModel
from .gemini_agent import GeminiAgent, GeminiModel
from .deepseek_agent import DeepSeekAgent, DeepSeekModel
from .claude_agent import ClaudeAgent, ClaudeModel
from .local_agent import LocalAgent, LocalModel
from .mlx_model_agent import MLXAgent, MLXModel
from .agent import Agent, DummyAgent, DummyModel


all_models = (
    [m for m in OpenAIModel]
    + [m for m in GeminiModel]
    + [m for m in ClaudeModel]
    + [m for m in DeepSeekModel]
    + [m for m in LocalModel]
    + [m for m in MLXModel]
    + [m for m in DummyModel]
)


def get_agent_by_model(model: StrEnum) -> Agent:
    if model in OpenAIModel:
        return OpenAIAgent(model)
    elif model in GeminiModel:
        return GeminiAgent(model)
    elif model in ClaudeModel:
        return ClaudeAgent(model)
    elif model in DeepSeekModel:
        return DeepSeekAgent(model)
    elif model in LocalModel:
        return LocalAgent(model)
    elif model in MLXModel:
        return MLXAgent(model)
    elif model in DummyModel:
        return DummyAgent(model)
    else:
        raise ValueError(f"Invalid model: {model}")
