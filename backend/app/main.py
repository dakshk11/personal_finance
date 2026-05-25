from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import advisor, ai_advisor, auth, backtests, data, filings, indices, market_history, option_strategy, personal_cfo, portfolio_analysis, portfolio_sync, portfolios, retirement_analyzer, rsi_playbook
from app.core.config import get_settings, local_cors_origins
from app.db.session import Base, SessionLocal, engine
from app.models import entities  # noqa: F401
from app.services.dev_seed import seed_local_test_account


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Simulation-only direct indexing, tax-loss harvesting, and backtesting API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=local_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_local_test_account(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(ai_advisor.router)
app.include_router(personal_cfo.router, prefix="/ai-advisor")
app.include_router(personal_cfo.router, prefix="/investing")
app.include_router(advisor.router)
app.include_router(indices.router)
app.include_router(data.router)
app.include_router(market_history.router)
app.include_router(option_strategy.router)
app.include_router(filings.router)
app.include_router(portfolio_analysis.router)
app.include_router(portfolio_sync.router)
app.include_router(portfolios.router)
app.include_router(backtests.router)
app.include_router(retirement_analyzer.router)
app.include_router(rsi_playbook.router)
