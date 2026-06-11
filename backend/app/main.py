from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api import advisor, ai_advisor, alpaca_quotes, auth, backtests, breakout_scanner, data, diversification, earnings_agent, filings, indices, market_history, option_strategy, optitrade_lab, personal_cfo, portfolio_analysis, portfolio_sync, portfolios, recommendation_agent, research_prompts, retirement_analyzer, rsi_playbook, sector_rotation, simulated_portfolios, smart_candles, stock_analysis, wheel_scanner_chat
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
    ensure_sector_rotation_accepted_allocation_columns()
    db = SessionLocal()
    try:
        seed_local_test_account(db)
    finally:
        db.close()


def ensure_sector_rotation_accepted_allocation_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    table_name = "sector_rotation_accepted_allocations"
    if table_name not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(table_name)}
    statements = []
    if "rebalance_date" not in existing:
        statements.append("ALTER TABLE sector_rotation_accepted_allocations ADD COLUMN rebalance_date DATE")
    if "rebalance_status" not in existing:
        statements.append("ALTER TABLE sector_rotation_accepted_allocations ADD COLUMN rebalance_status VARCHAR(32) DEFAULT 'planned'")
    if "rebalance_notes" not in existing:
        statements.append("ALTER TABLE sector_rotation_accepted_allocations ADD COLUMN rebalance_notes TEXT")
    if "updated_at" not in existing:
        statements.append("ALTER TABLE sector_rotation_accepted_allocations ADD COLUMN updated_at DATETIME")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(ai_advisor.router)
app.include_router(research_prompts.router)
app.include_router(alpaca_quotes.router)
app.include_router(optitrade_lab.router)
app.include_router(earnings_agent.router)
app.include_router(stock_analysis.router)
app.include_router(personal_cfo.router, prefix="/ai-advisor")
app.include_router(personal_cfo.router, prefix="/investing")
app.include_router(advisor.router)
app.include_router(indices.router)
app.include_router(data.router)
app.include_router(market_history.router)
app.include_router(option_strategy.router)
app.include_router(breakout_scanner.router)
app.include_router(smart_candles.router)
app.include_router(filings.router)
app.include_router(portfolio_analysis.router)
app.include_router(portfolio_sync.router)
app.include_router(portfolios.router)
app.include_router(backtests.router)
app.include_router(retirement_analyzer.router)
app.include_router(rsi_playbook.router)
app.include_router(diversification.router)
app.include_router(sector_rotation.router)
app.include_router(simulated_portfolios.router)
app.include_router(wheel_scanner_chat.router)
app.include_router(recommendation_agent.router)
