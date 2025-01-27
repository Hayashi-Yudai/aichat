from pydantic.dataclasses import dataclass

from roles import Agent, DeepSeekAgent, DummyAgent, OpenAIAgent


@dataclass
class AgentModel:
    org: str
    model_name: str


MODELS = [
    AgentModel(org="OpenAI", model_name="gpt-4o-mini"),
    AgentModel(org="OpenAI", model_name="gpt-4o"),
    AgentModel(org="OpenAI", model_name="o1-mini"),
    AgentModel(org="OpenAI", model_name="o1-preview"),
    AgentModel(org="Google", model_name="gemini-1.5-flash"),
    AgentModel(org="DeepSeek", model_name="deepseek-chat"),
    AgentModel(org="DeepSeek", model_name="deepseek-reasoner"),
    AgentModel(org="Dummy", model_name="Dummy"),  # debug用
]
DEFAULT_MODEL = "gpt-4o-mini"


def model_agent_mapping(model_name: str) -> Agent:
    model = None
    for m in MODELS:
        if m.model_name == model_name:
            model = m
            break

    if model is None:
        raise ValueError(f"Unknown model: {model_name}")

    match model.org:
        case "OpenAI":
            return OpenAIAgent(model_name)
        case "DeepSeek":
            return DeepSeekAgent(model_name)
        case "Dummy":
            return DummyAgent()
        case _:
            raise ValueError(f"Unknown model: {model_name}")
