from enum import StrEnum

from .openai_agent import OpenAIAgent, OpenAIModel
from .gemini_agent import GeminiAgent, GeminiModel
from .deepseek_agent import DeepSeekAgent, DeepSeekModel
from .claude_agent import ClaudeAgent, ClaudeModel
from .agent import Agent, DummyAgent, DummyModel


all_models = (
    [m for m in OpenAIModel]
    + [m for m in GeminiModel]
    + [m for m in ClaudeModel]
    + [m for m in DeepSeekModel]
    + [m for m in DummyModel]
)
model_agent_map: dict[StrEnum, Agent] = (
    {m: OpenAIAgent(m) for m in OpenAIModel}
    | {m: GeminiAgent(m) for m in GeminiModel}
    | {m: ClaudeAgent(m) for m in ClaudeModel}
    | {m: DeepSeekAgent(m) for m in DeepSeekModel}
    | {m: DummyAgent(m) for m in DummyModel}
)
