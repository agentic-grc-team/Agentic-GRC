# Agentic-GRC

AI-powered GRC assessment platform developed as part of the international student project.

| Folder | Contents |
|---|---|
| [`backend/`](backend/README.md) | FastAPI API, database models and migrations, services and tests |
| [`backend/app/agent/`](backend/app/agent/README.md) | Interview agent: LangGraph state machine over a local Ollama model |
| [`frontend/`](frontend/README.md) | Web application |
| [`docs/architecture.md`](docs/architecture.md) | Architecture and technical overview: components, login, organization isolation and roles, deployment |
| [`docs/decisions/`](docs/decisions/) | Architecture decision records |
| [`docs/design/`](docs/design/) | Design documents, such as the reasoning trace schema |
| [`docs/coding-standards.md`](docs/coding-standards.md) | Code style and local quality checks |

For local Ollama setup, configuration, benchmarks, and the alpha demo checklist, see [docs/ollama-setup.md](docs/ollama-setup.md).
