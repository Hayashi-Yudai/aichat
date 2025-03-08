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
