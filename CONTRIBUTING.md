# Contributing to FinanceOS

Thank you for your interest in contributing. FinanceOS is an educational personal finance platform — contributions that improve clarity, correctness, or usability are welcome.

## Before You Start

- Check [open issues](https://github.com/dakshk11/personal_finance/issues) to avoid duplicate work.
- For large changes, open an issue first to discuss the approach.
- All outputs in this project are educational and hypothetical. Keep that constraint in mind when adding features.

## Local Setup

Requirements: Docker Desktop (or compatible Docker engine) and Docker Compose.

```bash
git clone https://github.com/dakshk11/personal_finance.git
cd personal_finance
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

For backend-only or frontend-only runs, see the [Local Development Without Docker](README.md#local-development-without-docker) section in the README.

## Running Tests

Backend:

```bash
PYTHONPATH=backend pytest backend/tests
```

Frontend typecheck:

```bash
cd frontend && npm run typecheck
```

Frontend build:

```bash
cd frontend && npm run build
```

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR.
- Include a clear description of what changed and why.
- Run tests and typecheck before submitting.
- Do not commit `.env`, database files, real API keys, or any personal financial data.
- Follow existing code style — FastAPI + Pydantic on the backend, Next.js + TypeScript on the frontend.

## AI / Studio Features

The FinanceOS Studio features (Equity Research, Earnings Agent, Personal CFO) use a user-owned OpenAI API key that is encrypted before storage. When contributing to these features:

- Never log or expose the raw API key.
- Keep all AI outputs labeled as educational and not investment advice.
- Test with a real OpenAI key locally; do not hardcode or mock keys in tests.

## Disclaimer

FinanceOS is educational planning software only. Contributions must not introduce features that present outputs as investment, tax, legal, or trading advice.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
