# AIChat

An easy-to-customize AI Chat app powered by Flet.

![](images/app_view.png)

## Getting Started

To start the application, use the following commands:

```bash
$ uv sync
$ uv run flet run -d aichat/main.py  # To run as a desktop app
$ uv run flet run -w aichat/main.py  # To run as a web app
```

## Default Supported Models

The application supports the following models by default:

- OpenAI
- Claude
- Gemini
- DeepSeek

To use these models, make sure to set the required environment variables:

```
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
GEMINI_API_KEY=your_gemini_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
```

You can easily customize the models to suit your needs.

## How to Add New Models

To add a new model, you need to modify two files. First, create the agent settings for the model you want to use. Refer to [other agent definitions](https://github.com/Hayashi-Yudai/aichat/blob/main/aichat/agents/openai_agent.py) for examples and details.


```python
from enum import Enum

class YOURModel(str, Enum):  # Inherit from str and Enum directly
    MODEL1 = "model-1"  # e.g., GPT4O = "gpt-4o"


class YOURAGENT:
    def __init__(self, model: YOURModel):
        self.model = model
        self.role = Role(config.AGENT_NAME, config.AGENT_AVATAR_COLOR)
        self.client = ...  # e.g., self.client = OpenAI(api_key="YOUR_API_KEY")

    def _construct_request(self, message: Message) -> dict[str, Any]:
        """Construct the request in the format required by your model.
        e.g. {"role": "user", "content": "hoge"}
        """
        ...

    def request(self, messages: list[Message]) -> list[str]:
        """Sends a request to the agent and returns the response."""
        request_payload = [self._construct_request(m) for m in messages]
        response = ...
        return [response]
    
    def request_streaming(self, messages: list[Message]) -> Generator[str, None, None]:
        # if self.streamable is true, implement this method
        ...

```

Next, register the YOURModel and YOURAGENT classes with the system.  Modify the agents/__init__.py file as shown below:

```python
all_models = (
    [m for m in OpenAIModel]
    + [m for m in GeminiModel]
    + [m for m in ClaudeModel]
    + [m for m in DeepSeekModel]
    + [m for m in DummyModel]
    + [m for m in YOURModel]  # Append your model
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
    elif model in GemmaModel:
        return GemmaAgent(model)
    elif model in YOURModel:
        return YourAgent(model)  # Append your model and agent
    elif model in DummyModel:
        return DummyAgent(model)
    else:
        raise ValueError(f"Invalid model: {model}")

```