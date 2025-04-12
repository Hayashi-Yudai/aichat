import itertools
from enum import StrEnum

from .agent import Agent
from .openai_agent import OpenAIAgent, OpenAIModel
from .gemini_agent import GeminiAgent, GeminiModel
from .deepseek_agent import DeepSeekAgent, DeepSeekModel
from .claude_agent import ClaudeAgent, ClaudeModel
from .local_agent import LocalAgent, LocalModel
from .mlx_model_agent import MLXAgent, MLXModel
from .dummy_agent import DummyAgent, DummyModel


all_models = list(
    itertools.chain.from_iterable(
        [
            OpenAIModel,
            GeminiModel,
            ClaudeModel,
            DeepSeekModel,
            LocalModel,
            MLXModel,
            DummyModel,
        ]
    )
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
