from dataclasses import dataclass
from datetime import UTC, datetime, date, timedelta
import csv
import io
import json
from typing import Literal, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import PriceBar
from app.services.market_data import normalize_symbol


@dataclass(frozen=True)
class MajorIndex:
    symbol: str
    name: str
    benchmark: str
    category: str


@dataclass(frozen=True)
class HighYieldFund:
    symbol: str
    name: str
    issuer: str
    exposure: str
    strategy: str
    distribution_frequency: str
    source_url: str
    risk_note: str


@dataclass(frozen=True)
class HighYieldBacktest:
    evaluated_weeks: int
    buy_signals: int
    hit_rate_4w: float | None
    average_forward_return_4w: float | None
    last_buy_date: date | None
    recent_buy_dates: list[date]


@dataclass(frozen=True)
class HighYieldSignal:
    action: Literal["BUY", "HOLD"]
    signal_date: date | None
    last_close: float | None
    reason: str
    reasons: list[str]
    risk_state: str
    confidence: float
    limited_history: bool
    data_points: int
    backtest: HighYieldBacktest


@dataclass(frozen=True)
class HighYieldFundAnalysis:
    fund: HighYieldFund
    signal: HighYieldSignal
    last_price_date: date | None
    cached_at: datetime | None
    data_source: str
    warnings: list[str]


@dataclass(frozen=True)
class MarketHistoryBar:
    date: date
    close: float
    adjusted_close: float
    dividend: float
    source: str


@dataclass(frozen=True)
class MarketHistory:
    symbol: str
    name: str
    benchmark: str
    category: str
    requested_start_date: date
    requested_end_date: date
    start_date: date | None
    end_date: date | None
    bars: list[MarketHistoryBar]
    warnings: list[str]


MAJOR_INDEXES: tuple[MajorIndex, ...] = (
    MajorIndex("SPY", "SPDR S&P 500 ETF Trust", "S&P 500", "Large-cap U.S. equity"),
    MajorIndex("VOO", "Vanguard S&P 500 ETF", "S&P 500", "Large-cap U.S. equity"),
    MajorIndex("QQQ", "Invesco QQQ Trust", "Nasdaq-100", "Large-cap growth"),
    MajorIndex("DIA", "SPDR Dow Jones Industrial Average ETF", "Dow Jones Industrial Average", "Large-cap blue chip"),
    MajorIndex("IWM", "iShares Russell 2000 ETF", "Russell 2000", "Small-cap U.S. equity"),
    MajorIndex("VTI", "Vanguard Total Stock Market ETF", "CRSP U.S. Total Market", "Total U.S. equity"),
    MajorIndex("EFA", "iShares MSCI EAFE ETF", "MSCI EAFE", "Developed international equity"),
    MajorIndex("EEM", "iShares MSCI Emerging Markets ETF", "MSCI Emerging Markets", "Emerging markets equity"),
    MajorIndex("AGG", "iShares Core U.S. Aggregate Bond ETF", "Bloomberg U.S. Aggregate Bond", "Core U.S. bonds"),
)

MAJOR_INDEX_BY_SYMBOL = {item.symbol: item for item in MAJOR_INDEXES}

HIGH_YIELD_FUNDS: tuple[HighYieldFund, ...] = (
    HighYieldFund(
        symbol="QQQI",
        name="NEOS Nasdaq-100 High Income ETF",
        issuer="NEOS",
        exposure="Nasdaq-100 equity exposure",
        strategy="Owns Nasdaq-100 constituents and uses a data-driven NDX call option strategy to seek high monthly income with some upside participation.",
        distribution_frequency="Monthly",
        source_url="https://neosfunds.com/qqqi/",
        risk_note="Options income can cap upside and distributions may include return of capital, so NAV erosion and equity drawdowns still matter.",
    ),
    HighYieldFund(
        symbol="SPYI",
        name="NEOS S&P 500 High Income ETF",
        issuer="NEOS",
        exposure="S&P 500 equity exposure",
        strategy="Owns S&P 500 constituents and uses SPX index options to seek tax-efficient monthly income and partial upside participation.",
        distribution_frequency="Monthly",
        source_url="https://neosfunds.com/spyi/",
        risk_note="Broad equity exposure remains exposed to market losses, and option-income distributions are not a substitute for total return.",
    ),
    HighYieldFund(
        symbol="CHPY",
        name="YieldMax Semiconductor Portfolio Option Income ETF",
        issuer="YieldMax",
        exposure="Concentrated semiconductor equities",
        strategy="Actively holds a focused semiconductor stock portfolio and sells call spreads to harvest option premium with a weekly distribution objective.",
        distribution_frequency="Weekly",
        source_url="https://yieldmaxetfs.com/our-etfs/chpy/",
        risk_note="Semiconductor concentration, derivatives, high turnover, and weekly distributions can create high volatility and NAV erosion risk.",
    ),
    HighYieldFund(
        symbol="IAUI",
        name="NEOS Gold High Income ETF",
        issuer="NEOS",
        exposure="Gold ETP exposure",
        strategy="Pairs exposure to gold exchange-traded products with a data-driven call option strategy to seek high monthly income and gold-linked appreciation.",
        distribution_frequency="Monthly",
        source_url="https://neosfunds.com/iaui/",
        risk_note="Gold and options can both be volatile, and distributions may include return of capital rather than recurring investment income.",
    ),
    HighYieldFund(
        symbol="OVL",
        name="Overlay Shares Large Cap Equity ETF",
        issuer="Liquid Strategies",
        exposure="U.S. large-cap equity exposure",
        strategy="Combines large-cap passive equity exposure with an active risk-managed put-selling overlay intended to generate additional income.",
        distribution_frequency="Monthly",
        source_url="https://lsfunds.com/ovl",
        risk_note="Put-spread overlays can lose money during sharp selloffs and the fund can still decline with large-cap equities.",
    ),
    HighYieldFund(
        symbol="GIAX",
        name="Nicholas Global Equity and Income ETF",
        issuer="XFunds / Nicholas",
        exposure="Global equity ETFs and selected holdings",
        strategy="Uses global equity ETF exposure and sells short-dated index credit call spreads to seek current income with secondary capital appreciation.",
        distribution_frequency="Weekly",
        source_url="https://nicholasx.com/giax/",
        risk_note="Credit call spreads, global equity exposure, and recurring distributions can limit upside and may erode NAV during poor market conditions.",
    ),
)

HIGH_YIELD_BY_SYMBOL = {item.symbol: item for item in HIGH_YIELD_FUNDS}


def list_major_indexes() -> list[MajorIndex]:
    return list(MAJOR_INDEXES)


def list_high_yield_fund_metadata() -> list[HighYieldFund]:
    return list(HIGH_YIELD_FUNDS)


def cache_major_index_history(db: Session, start_date: date, end_date: date, force_refresh: bool = False) -> list[MarketHistory]:
    return [
        get_market_history(db, item.symbol, start_date, end_date, force_refresh=force_refresh)
        for item in MAJOR_INDEXES
    ]


def cache_high_yield_history(
    db: Session,
    start_date: date,
    end_date: date,
    force_refresh: bool = False,
) -> list[HighYieldFundAnalysis]:
    return [
        get_high_yield_analysis(db, item.symbol, start_date, end_date, force_refresh=force_refresh)
        for item in HIGH_YIELD_FUNDS
    ]


def get_high_yield_analysis(
    db: Session,
    symbol: str,
    start_date: date,
    end_date: date,
    force_refresh: bool = False,
) -> HighYieldFundAnalysis:
    normalized = normalize_symbol(symbol)
    fund = HIGH_YIELD_BY_SYMBOL.get(normalized)
    if fund is None:
        raise ValueError(f"{normalized} is not configured as a high-yield fund.")

    history = get_market_history(db, normalized, start_date, end_date, force_refresh=force_refresh)
    signal = calculate_high_yield_signal(history.bars)
    warnings = list(history.warnings)
    if signal.limited_history:
        warnings.append("Limited cached history is available; the model is showing HOLD instead of a buy signal.")

    return HighYieldFundAnalysis(
        fund=fund,
        signal=signal,
        last_price_date=history.end_date,
        cached_at=_latest_cache_at(db, normalized),
        data_source=history.bars[-1].source if history.bars else "No cached provider history",
        warnings=warnings,
    )


def get_market_history(
    db: Session,
    symbol: str,
    start_date: date,
    end_date: date,
    force_refresh: bool = False,
) -> MarketHistory:
    normalized = normalize_symbol(symbol)
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    cached = _cached_rows(db, normalized, start_date, end_date)
    should_fetch = force_refresh or _needs_provider_refresh(cached, start_date, end_date)
    warnings: list[str] = []
    if should_fetch:
        fetched = _fetch_provider_history(normalized, start_date, end_date)
        if fetched:
            _upsert_price_bars(db, normalized, fetched)
            cached = _cached_rows(db, normalized, start_date, end_date)
        else:
            warnings.append(f"Could not download provider history for {normalized}; using any cached rows already available.")

    bars = [
        MarketHistoryBar(
            date=row.price_date,
            close=round(row.close, 4),
            adjusted_close=round(row.adjusted_close, 4),
            dividend=round(row.dividend or 0, 6),
            source=row.source,
        )
        for row in cached
    ]
    if not bars:
        warnings.append(f"No cached market history is available for {normalized} in the requested date range.")

    high_yield_fund = HIGH_YIELD_BY_SYMBOL.get(normalized)
    meta = MAJOR_INDEX_BY_SYMBOL.get(normalized)
    if meta is None and high_yield_fund:
        meta = MajorIndex(normalized, high_yield_fund.name, high_yield_fund.exposure, "High-yield income ETF")
    if meta is None:
        meta = MajorIndex(normalized, f"{normalized} market history", normalized, "User-entered symbol")
    return MarketHistory(
        symbol=normalized,
        name=meta.name,
        benchmark=meta.benchmark,
        category=meta.category,
        requested_start_date=start_date,
        requested_end_date=end_date,
        start_date=bars[0].date if bars else None,
        end_date=bars[-1].date if bars else None,
        bars=bars,
        warnings=warnings,
    )


def calculate_high_yield_signal(bars: list[MarketHistoryBar]) -> HighYieldSignal:
    ordered = sorted(
        [bar for bar in bars if bar.adjusted_close > 0 or bar.close > 0],
        key=lambda bar: bar.date,
    )
    prices = [bar.adjusted_close if bar.adjusted_close > 0 else bar.close for bar in ordered]
    dates = [bar.date for bar in ordered]
    if len(prices) < 90:
        return HighYieldSignal(
            action="HOLD",
            signal_date=dates[-1] if dates else None,
            last_close=round(prices[-1], 4) if prices else None,
            reason="Limited daily history; wait for at least 90 cached trading days before adding new money.",
            reasons=["Limited history"],
            risk_state="Limited history",
            confidence=0.2,
            limited_history=True,
            data_points=len(prices),
            backtest=HighYieldBacktest(
                evaluated_weeks=0,
                buy_signals=0,
                hit_rate_4w=None,
                average_forward_return_4w=None,
                last_buy_date=None,
                recent_buy_dates=[],
            ),
        )

    weekly_indexes = _weekly_close_indexes(dates)
    backtest, latest_decision = _weekly_high_yield_backtest(prices, dates, weekly_indexes)
    return HighYieldSignal(
        action=cast(Literal["BUY", "HOLD"], latest_decision["action"]),
        signal_date=dates[cast(int, latest_decision["index"])],
        last_close=round(prices[cast(int, latest_decision["index"])], 4),
        reason=cast(str, latest_decision["reason"]),
        reasons=cast(list[str], latest_decision["reasons"]),
        risk_state=cast(str, latest_decision["risk_state"]),
        confidence=cast(float, latest_decision["confidence"]),
        limited_history=False,
        data_points=len(prices),
        backtest=backtest,
    )


def _weekly_high_yield_backtest(
    prices: list[float],
    dates: list[date],
    weekly_indexes: list[int],
) -> tuple[HighYieldBacktest, dict[str, object]]:
    last_buy_week: int | None = None
    buy_dates: list[date] = []
    forward_returns: list[float] = []
    hits = 0
    latest_decision: dict[str, object] = {
        "action": "HOLD",
        "index": len(prices) - 1,
        "reason": "No weekly evaluation date was available.",
        "reasons": ["No weekly evaluation date"],
        "risk_state": "Unknown",
        "confidence": 0.2,
    }
    evaluated_weeks = 0

    for week_number, price_index in enumerate(weekly_indexes):
        if price_index < 89:
            continue
        evaluated_weeks += 1
        if last_buy_week is None:
            weeks_since_last_buy = week_number + 1
        else:
            weeks_since_last_buy = week_number - last_buy_week
        decision = _evaluate_high_yield_week(prices, dates, price_index, weeks_since_last_buy)
        latest_decision = decision
        if decision["action"] == "BUY":
            buy_dates.append(dates[price_index])
            forward_index = price_index + 20
            if forward_index < len(prices):
                forward_return = (prices[forward_index] / prices[price_index]) - 1
                forward_returns.append(forward_return)
                if forward_return > 0:
                    hits += 1
            last_buy_week = week_number

    hit_rate = hits / len(forward_returns) if forward_returns else None
    average_forward = average(forward_returns) if forward_returns else None
    return (
        HighYieldBacktest(
            evaluated_weeks=evaluated_weeks,
            buy_signals=len(buy_dates),
            hit_rate_4w=round(hit_rate, 4) if hit_rate is not None else None,
            average_forward_return_4w=round(average_forward, 4) if average_forward is not None else None,
            last_buy_date=buy_dates[-1] if buy_dates else None,
            recent_buy_dates=buy_dates[-6:],
        ),
        latest_decision,
    )


def _evaluate_high_yield_week(
    prices: list[float],
    dates: list[date],
    index: int,
    weeks_since_last_buy: int,
) -> dict[str, object]:
    price = prices[index]
    sma20 = _sma_at(prices, index, 20)
    sma50 = _sma_at(prices, index, 50)
    sma200 = _sma_at(prices, index, 200)
    sma50_prior = _sma_at(prices, index - 10, 50)
    rsi14 = _rsi_at(prices, index, 14)
    high63 = max(prices[max(0, index - 62):index + 1])
    return63 = (price / prices[index - 63]) - 1 if index >= 63 and prices[index - 63] > 0 else 0
    drawdown63 = (price / high63) - 1 if high63 > 0 else 0
    reasons: list[str] = []

    severe_long_trend = bool(sma200 and price < sma200 * 0.92)
    severe_recent_return = return63 < -0.12
    deteriorating_50d = bool(sma50 and sma50_prior and sma50 < sma50_prior * 0.985)
    severe = severe_long_trend or severe_recent_return or deteriorating_50d

    if severe_long_trend:
        reasons.append("Price is more than 8% below the 200-day average")
    if severe_recent_return:
        reasons.append("63-day return is below -12%")
    if deteriorating_50d:
        reasons.append("50-day trend is deteriorating")

    pullback_to_20d = bool(sma20 and price <= sma20 * 0.985)
    pullback_rsi = bool(rsi14 is not None and rsi14 < 45)
    pullback_drawdown = drawdown63 <= -0.04
    if pullback_to_20d:
        reasons.append("Price is at least 1.5% below the 20-day average")
    if pullback_rsi:
        reasons.append("RSI(14) is below 45")
    if pullback_drawdown:
        reasons.append("Price is at least 4% below the 63-day high")

    sma50_rising = bool(sma50 and sma50_prior and sma50 >= sma50_prior)
    trend_ok = bool((sma200 and price >= sma200) or (sma50_rising and sma20 and price >= sma20))
    scheduled_buy = bool(
        not severe
        and weeks_since_last_buy >= 4
        and sma50
        and price >= sma50
    )

    if severe:
        return {
            "action": "HOLD",
            "index": index,
            "reason": "Risk-off filter is active; hold existing shares but skip this weekly add.",
            "reasons": reasons,
            "risk_state": "Risk-off",
            "confidence": 0.32,
        }

    if trend_ok and (pullback_to_20d or pullback_rsi or pullback_drawdown):
        reasons.insert(0, "Controlled pullback with trend support")
        return {
            "action": "BUY",
            "index": index,
            "reason": "Controlled pullback while the longer trend remains acceptable.",
            "reasons": reasons,
            "risk_state": "Trend-supported pullback",
            "confidence": 0.68,
        }

    if scheduled_buy:
        return {
            "action": "BUY",
            "index": index,
            "reason": "Scheduled DCA add: no buy signal fired for four weekly checks and price remains above the 50-day average.",
            "reasons": ["Four-week scheduled DCA window", "Price remains above the 50-day average"],
            "risk_state": "Scheduled DCA window",
            "confidence": 0.55,
        }

    neutral_reasons = reasons or ["No controlled pullback or scheduled DCA window this week"]
    return {
        "action": "HOLD",
        "index": index,
        "reason": "No new-add setup this week; long-term holdings remain buy-and-hold positions.",
        "reasons": neutral_reasons,
        "risk_state": "Neutral",
        "confidence": 0.45,
    }


def _weekly_close_indexes(dates: list[date]) -> list[int]:
    indexes: list[int] = []
    current_week: tuple[int, int] | None = None
    for index, value in enumerate(dates):
        iso = value.isocalendar()
        key = (iso.year, iso.week)
        if key != current_week:
            indexes.append(index)
            current_week = key
        else:
            indexes[-1] = index
    return indexes


def _sma_at(values: list[float], index: int, period: int) -> float | None:
    if index < 0 or index + 1 < period:
        return None
    return average(values[index - period + 1:index + 1])


def _rsi_at(values: list[float], index: int, period: int) -> float | None:
    if index < period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for cursor in range(index - period + 1, index + 1):
        delta = values[cursor] - values[cursor - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(delta))
    average_gain = average(gains)
    average_loss = average(losses)
    if average_loss == 0:
        return 100
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def average(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def _latest_cache_at(db: Session, symbol: str) -> datetime | None:
    return db.scalar(select(func.max(PriceBar.retrieved_at)).where(PriceBar.symbol == symbol))


def _cached_rows(db: Session, symbol: str, start_date: date, end_date: date) -> list[PriceBar]:
    return list(
        db.scalars(
            select(PriceBar)
            .where(
                PriceBar.symbol == symbol,
                PriceBar.price_date >= start_date,
                PriceBar.price_date <= end_date,
            )
            .order_by(PriceBar.price_date)
        )
    )


def _needs_provider_refresh(rows: list[PriceBar], start_date: date, end_date: date) -> bool:
    if any(row.source == "deterministic offline fallback" for row in rows):
        return True
    if not rows:
        return True
    business_days = _business_day_count(start_date, end_date)
    if business_days <= 8:
        return len(rows) < max(1, business_days // 2)
    return len(rows) < business_days * 0.55


def _fetch_provider_history(symbol: str, start_date: date, end_date: date) -> list[MarketHistoryBar]:
    return (
        _fetch_yahoo_chart_history(symbol, start_date, end_date)
        or _fetch_yfinance_history(symbol, start_date, end_date)
        or _fetch_stooq_history(symbol, start_date, end_date)
    )


def _fetch_yahoo_chart_history(symbol: str, start_date: date, end_date: date) -> list[MarketHistoryBar]:
    period1 = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC).timestamp())
    period2_date = end_date + timedelta(days=1)
    period2 = int(datetime(period2_date.year, period2_date.month, period2_date.day, tzinfo=UTC).timestamp())
    query = urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "div,splits",
        }
    )
    request = Request(
        f"https://query2.finance.yahoo.com/v8/finance/chart/{_provider_symbol(symbol)}?{query}",
        headers={"User-Agent": "Mozilla/5.0 DirectIndex local research"},
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except Exception:
        return []

    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return []
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    adjusted = indicators.get("adjclose") or []
    if not timestamps or not quotes:
        return []
    close_values = quotes[0].get("close") or []
    adjusted_values = adjusted[0].get("adjclose") if adjusted else []
    dividends_by_date: dict[date, float] = {}
    events = result.get("events") or {}
    dividends = events.get("dividends") or {}
    if isinstance(dividends, dict):
        for event in dividends.values():
            if not isinstance(event, dict):
                continue
            event_date = _date_from_epoch(event.get("date"))
            amount = _safe_float(event.get("amount"))
            if event_date and amount:
                dividends_by_date[event_date] = dividends_by_date.get(event_date, 0) + amount

    bars: list[MarketHistoryBar] = []
    for index, timestamp in enumerate(timestamps):
        price_date = _date_from_epoch(timestamp)
        if not price_date:
            continue
        close = _safe_float(close_values[index] if index < len(close_values) else None)
        adjusted_close = _safe_float(adjusted_values[index] if adjusted_values and index < len(adjusted_values) else None)
        if close is None or close <= 0:
            continue
        bars.append(
            MarketHistoryBar(
                date=price_date,
                close=round(close, 4),
                adjusted_close=round(adjusted_close if adjusted_close and adjusted_close > 0 else close, 4),
                dividend=round(dividends_by_date.get(price_date, 0), 6),
                source="yahoo chart adjusted close cache",
            )
        )
    return bars


def _fetch_yfinance_history(symbol: str, start_date: date, end_date: date) -> list[MarketHistoryBar]:
    try:
        import yfinance as yf
    except Exception:
        return []

    try:
        history = yf.Ticker(_provider_symbol(symbol)).history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
        )
    except Exception:
        return []
    if history is None or history.empty or "Close" not in history:
        return []

    bars: list[MarketHistoryBar] = []
    for index, row in history.iterrows():
        price_date = getattr(index, "date", lambda: None)()
        if not isinstance(price_date, date):
            continue
        close = _safe_float(row.get("Close"))
        adjusted_close = _safe_float(row.get("Adj Close")) or close
        if close is None or adjusted_close is None or close <= 0 or adjusted_close <= 0:
            continue
        dividend = _safe_float(row.get("Dividends")) or 0
        bars.append(
            MarketHistoryBar(
                date=price_date,
                close=round(close, 4),
                adjusted_close=round(adjusted_close, 4),
                dividend=round(dividend, 6),
                source="yfinance adjusted close cache",
            )
        )
    return bars


def _fetch_stooq_history(symbol: str, start_date: date, end_date: date) -> list[MarketHistoryBar]:
    query = urlencode(
        {
            "s": f"{_provider_symbol(symbol).lower()}.us",
            "i": "d",
            "d1": start_date.strftime("%Y%m%d"),
            "d2": end_date.strftime("%Y%m%d"),
        }
    )
    url = f"https://stooq.com/q/d/l/?{query}"
    try:
        with urlopen(url, timeout=12) as response:
            payload = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    bars: list[MarketHistoryBar] = []
    for row in csv.DictReader(io.StringIO(payload)):
        try:
            price_date = date.fromisoformat(str(row.get("Date", "")))
            close = float(str(row.get("Close", "")).replace(",", ""))
        except ValueError:
            continue
        if close <= 0:
            continue
        bars.append(
            MarketHistoryBar(
                date=price_date,
                close=round(close, 4),
                adjusted_close=round(close, 4),
                dividend=0,
                source="stooq daily close cache",
            )
        )
    return bars


def _upsert_price_bars(db: Session, symbol: str, bars: list[MarketHistoryBar]) -> None:
    existing = {
        row.price_date: row
        for row in db.scalars(
            select(PriceBar).where(
                PriceBar.symbol == symbol,
                PriceBar.price_date.in_([bar.date for bar in bars]),
            )
        )
    }
    for bar in bars:
        row = existing.get(bar.date)
        if row:
            row.close = bar.close
            row.adjusted_close = bar.adjusted_close
            row.dividend = bar.dividend
            row.split_ratio = 1
            row.source = bar.source
            db.add(row)
        else:
            db.add(
                PriceBar(
                    symbol=symbol,
                    price_date=bar.date,
                    close=bar.close,
                    adjusted_close=bar.adjusted_close,
                    dividend=bar.dividend,
                    split_ratio=1,
                    source=bar.source,
                )
            )
    db.commit()


def _provider_symbol(symbol: str) -> str:
    return normalize_symbol(symbol).replace(".", "-")


def _safe_float(value: object) -> float | None:
    try:
        converted = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if converted != converted:
        return None
    return converted


def _date_from_epoch(value: object) -> date | None:
    try:
        timestamp = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, UTC).date()


def _business_day_count(start_date: date, end_date: date) -> int:
    total = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            total += 1
        current += timedelta(days=1)
    return total
