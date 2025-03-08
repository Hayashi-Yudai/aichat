from enum import StrEnum

from .openai_agent import OpenAIAgent, OpenAIModel
from .gemini_agent import GeminiAgent, GeminiModel
from .agent import Agent, DummyAgent, DummyModel


all_models = (
    [m for m in OpenAIModel] + [m for m in GeminiModel] + [m for m in DummyModel]
)
model_agent_map: dict[StrEnum, Agent] = (
    {m: OpenAIAgent(m) for m in OpenAIModel}
    | {m: GeminiAgent(m) for m in GeminiModel}
    | {m: DummyAgent(m) for m in DummyModel}
)
