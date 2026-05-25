from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import json
import math
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import (
    OptionStrategyAlertEvent,
    OptionStrategyConfigState,
    OptionStrategyScanRun,
    OptionStrategySignalCandidate,
    OptionStrategyWheelPosition,
)
from app.services.index_data import INDEX_DEFINITIONS
from app.services.market_data import normalize_symbol
from app.services.market_history import MarketHistory, MarketHistoryBar, get_market_history


LEGACY_DEFAULT_TICKERS = ["TQQQ", "SOXL", "UPRO", "QQQ", "SPY", "SMH"]
DEFAULT_CORE_TICKERS = ["QQQ", "SPY", "SMH", "XLE", "XLI"]
DEFAULT_LEVERAGED_TICKERS = ["UPRO", "TQQQ", "SOXL"]
DEFAULT_EXTRA_TICKERS = DEFAULT_CORE_TICKERS + DEFAULT_LEVERAGED_TICKERS
DEFAULT_UNIVERSE_GROUPS = ["sp500_top_30", "nasdaq_top_30", "core_etfs", "leveraged_etfs"]
DEFAULT_EMA_PERIODS = [8, 21, 34, 55]
OPTION_CHAIN_SOURCE = "yfinance live option chain + cached market history"
FALLBACK_CHAIN_SOURCE = "yfinance live option chain with deterministic fallback contracts"
RISK_FREE_RATE = 0.045
DEFAULT_TARGET_DELTA_MIN = 0.20
DEFAULT_TARGET_DELTA_MAX = 0.35
DEFAULT_MIN_IV_RANK = 0.40
DEFAULT_BB_PERCENT_MAX = 0.75
DEFAULT_EARNINGS_EXCLUSION_DAYS = 7
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MAX_SPREAD_PCT = 0.15
DEFAULT_PROFIT_TAKE_PCT = 0.50
DEFAULT_SINGLE_NAME_CAP = 0.10
DEFAULT_SECTOR_CAP = 0.25
US_MARKET_TIME_ZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class UniverseItem:
    symbol: str
    name: str
    sector: str
    group: str


@dataclass(frozen=True)
class PutContract:
    strike: float
    expiration: date
    dte: int
    bid: float
    ask: float
    mid: float
    iv: float
    open_interest: int
    volume: int | None
    provider: str

_BASE_IV = {
    "TQQQ": 0.68,
    "SOXL": 0.74,
    "UPRO": 0.54,
    "QQQ": 0.52,
    "SPY": 0.41,
    "SMH": 0.57,
}

_BASE_YIELD = {
    "TQQQ": 0.056,
    "SOXL": 0.062,
    "UPRO": 0.043,
    "QQQ": 0.051,
    "SPY": 0.032,
    "SMH": 0.053,
}

_SYNTHETIC_BASE_PRICE = {
    "TQQQ": 78.0,
    "SOXL": 44.0,
    "UPRO": 82.0,
    "QQQ": 452.0,
    "SPY": 526.0,
    "SMH": 248.0,
    "XLE": 92.0,
    "XLI": 128.0,
}


def default_universe() -> list[dict[str, str]]:
    items = _default_universe_items()
    return [
        {
            "symbol": item.symbol,
            "name": item.name,
            "sector": item.sector,
            "group": item.group,
        }
        for item in items
    ]


def get_config(db: Session, user_id: int) -> dict[str, Any]:
    row = _get_or_create_config(db, user_id)
    return _config_out(row)


def update_config(db: Session, user_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    row = _get_or_create_config(db, user_id)
    if "tickers" in updates and updates["tickers"] is not None:
        tickers = [normalize_symbol(str(symbol)) for symbol in updates["tickers"] if str(symbol).strip()]
        row.tickers_json = json.dumps(tickers or _default_tickers())
    if "account_value" in updates and updates["account_value"] is not None:
        row.account_value = float(updates["account_value"])
    if "exposure_cap" in updates and updates["exposure_cap"] is not None:
        row.exposure_cap = float(updates["exposure_cap"])
    if "dte_min" in updates and updates["dte_min"] is not None:
        row.dte_min = int(updates["dte_min"])
    if "dte_max" in updates and updates["dte_max"] is not None:
        row.dte_max = int(updates["dte_max"])
    if row.dte_min > row.dte_max:
        row.dte_min, row.dte_max = row.dte_max, row.dte_min
    if "rsi_period" in updates and updates["rsi_period"] is not None:
        row.rsi_period = int(updates["rsi_period"])
    if "rsi_max" in updates and updates["rsi_max"] is not None:
        row.rsi_max = float(updates["rsi_max"])
    if "ema_periods" in updates and updates["ema_periods"] is not None:
        periods = [int(period) for period in updates["ema_periods"] if int(period) > 1]
        row.ema_periods_json = json.dumps(periods[:4] or DEFAULT_EMA_PERIODS)
    if "min_iv" in updates and updates["min_iv"] is not None:
        row.min_iv = float(updates["min_iv"])
    if "min_premium_yield" in updates and updates["min_premium_yield"] is not None:
        row.min_premium_yield = float(updates["min_premium_yield"])
    if "webhook_url" in updates:
        row.webhook_url = updates["webhook_url"] or None
    db.commit()
    db.refresh(row)
    return _config_out(row)


def run_scan(db: Session, user_id: int, force: bool = False) -> dict[str, Any]:
    config_row = _get_or_create_config(db, user_id)
    config = _config_out(config_row)
    today = _market_date_today()
    if not force:
        cached = _latest_scan_run_for_date(db, user_id, today)
        if cached:
            rows = db.scalars(
                select(OptionStrategySignalCandidate)
                .where(OptionStrategySignalCandidate.user_id == user_id, OptionStrategySignalCandidate.scan_run_id == cached.id)
                .order_by(OptionStrategySignalCandidate.rank, OptionStrategySignalCandidate.id)
            ).all()
            if rows:
                return _scan_result_out(cached, rows)

    start_date = today - timedelta(days=370)
    warnings: list[str] = [
        "Signal-only scanner. No trades are placed and generated opportunities are not financial advice.",
        "Live option chains are sourced from yfinance when available; fallback contracts are labeled when provider data is unavailable.",
    ]

    scan_run = OptionStrategyScanRun(user_id=user_id, data_source=OPTION_CHAIN_SOURCE, warnings_json="[]")
    db.add(scan_run)
    db.flush()

    all_candidates: list[dict[str, Any]] = []
    used_fallback = False
    for symbol in config["tickers"]:
        history = _safe_market_history(db, symbol, start_date, today)
        warnings.extend(f"{symbol}: {warning}" for warning in history.warnings)
        candidates = _build_symbol_candidates(db, user_id, config, history)
        if any(candidate["provider"] != "yfinance" for candidate in candidates):
            used_fallback = True
        all_candidates.extend(candidates)

    if used_fallback:
        scan_run.data_source = FALLBACK_CHAIN_SOURCE
    all_candidates.sort(key=lambda item: (item["status"] != "approved", -item["score"], -item["premium_yield"], -item["open_interest"], item["symbol"]))
    persisted: list[OptionStrategySignalCandidate] = []
    for rank, candidate in enumerate(all_candidates, start=1):
        candidate["deep_dive_rank"] = rank if rank <= 5 else None
        candidate["deep_dive_summary"] = _deep_dive_summary(candidate, rank)
        row = OptionStrategySignalCandidate(
            user_id=user_id,
            scan_run_id=scan_run.id,
            rank=rank,
            symbol=candidate["symbol"],
            action=candidate["action"],
            status=candidate["status"],
            underlying_price=candidate["underlying_price"],
            strike=candidate["strike"],
            expiration=candidate["expiration"],
            dte=candidate["dte"],
            delta=candidate["delta"],
            iv=candidate["iv"],
            bid=candidate["bid"],
            ask=candidate["ask"],
            mid=candidate["mid"],
            open_interest=candidate["open_interest"],
            premium_yield=candidate["premium_yield"],
            collateral=candidate["collateral"],
            alert_target_price=candidate["alert_target_price"],
            exposure_usage=candidate["exposure_usage"],
            checklist_json=json.dumps(candidate["checklist"]),
            blocked_reasons_json=json.dumps(candidate["blocked_reasons"]),
            created_at=scan_run.scanned_at,
        )
        db.add(row)
        persisted.append(row)

    scan_run.warnings_json = json.dumps(_dedupe(warnings))
    db.commit()
    db.refresh(scan_run)
    for row in persisted:
        db.refresh(row)
    return _scan_result_out(scan_run, persisted)


def list_signals(db: Session, user_id: int) -> list[dict[str, Any]]:
    scan_run = _latest_scan_run(db, user_id)
    if scan_run is None:
        return run_scan(db, user_id, force=False)["signals"]
    rows = db.scalars(
        select(OptionStrategySignalCandidate)
        .where(OptionStrategySignalCandidate.user_id == user_id, OptionStrategySignalCandidate.scan_run_id == scan_run.id)
        .order_by(OptionStrategySignalCandidate.rank, OptionStrategySignalCandidate.id)
    ).all()
    if not rows:
        return run_scan(db, user_id, force=False)["signals"]
    return [_signal_out(row) for row in rows]


def list_positions(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(OptionStrategyWheelPosition)
        .where(OptionStrategyWheelPosition.user_id == user_id, OptionStrategyWheelPosition.status != "closed")
        .order_by(desc(OptionStrategyWheelPosition.updated_at), desc(OptionStrategyWheelPosition.id))
    ).all()
    return [_position_out(row) for row in rows]


def list_alerts(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(OptionStrategyAlertEvent)
        .where(OptionStrategyAlertEvent.user_id == user_id)
        .order_by(desc(OptionStrategyAlertEvent.created_at), desc(OptionStrategyAlertEvent.id))
        .limit(50)
    ).all()
    return [_alert_out(row) for row in rows]


def record_position_event(db: Session, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    event = str(payload.get("event") or "").strip().lower()
    if event == "accepted_put":
        return _record_accepted_put(db, user_id, payload)
    if event == "assigned":
        return _record_assignment(db, user_id, payload)
    if event == "closed":
        return _record_closed(db, user_id, payload)
    raise ValueError("Unsupported option strategy position event.")


def reset_option_strategy_state(db: Session, user_id: int) -> None:
    db.query(OptionStrategyAlertEvent).filter(OptionStrategyAlertEvent.user_id == user_id).delete()
    db.query(OptionStrategyWheelPosition).filter(OptionStrategyWheelPosition.user_id == user_id).delete()
    db.query(OptionStrategySignalCandidate).filter(OptionStrategySignalCandidate.user_id == user_id).delete()
    db.query(OptionStrategyScanRun).filter(OptionStrategyScanRun.user_id == user_id).delete()
    db.query(OptionStrategyConfigState).filter(OptionStrategyConfigState.user_id == user_id).delete()
    db.commit()


def _record_accepted_put(db: Session, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    candidate_id = _optional_int(payload.get("signal_candidate_id"))
    candidate_row = None
    if candidate_id is not None:
        candidate_row = db.scalar(
            select(OptionStrategySignalCandidate).where(
                OptionStrategySignalCandidate.user_id == user_id,
                OptionStrategySignalCandidate.id == candidate_id,
            )
        )
        existing = db.scalar(
            select(OptionStrategyWheelPosition).where(
                OptionStrategyWheelPosition.user_id == user_id,
                OptionStrategyWheelPosition.signal_candidate_id == candidate_id,
                OptionStrategyWheelPosition.status != "closed",
            )
        )
        if existing:
            return _position_out(existing)

    candidate = _candidate_payload_from_row(candidate_row) if candidate_row else dict(payload.get("candidate") or {})
    if not candidate:
        raise ValueError("Accepted put requires a signal candidate.")

    symbol = normalize_symbol(str(candidate.get("symbol") or ""))
    if not symbol:
        raise ValueError("Accepted put requires a symbol.")

    position = OptionStrategyWheelPosition(
        user_id=user_id,
        signal_candidate_id=candidate_row.id if candidate_row else None,
        symbol=symbol,
        status="put_open",
        option_type="put",
        strike=float(candidate.get("strike") or 0),
        expiration=_parse_date(candidate.get("expiration")),
        contracts=int(candidate.get("contracts") or 1),
        entry_premium=float(candidate.get("mid") or candidate.get("entry_premium") or 0),
        current_price=float(candidate.get("mid") or candidate.get("current_price") or 0),
        alert_target_price=float(candidate.get("alert_target_price") or 0),
        collateral=float(candidate.get("collateral") or 0),
    )
    db.add(position)
    db.flush()

    db.add(
        OptionStrategyAlertEvent(
            user_id=user_id,
            position_id=position.id,
            symbol=symbol,
            kind="profit_50",
            status="open",
            message=f"{symbol} put close alert armed at 50% of entry premium.",
            target_price=position.alert_target_price,
            current_price=position.current_price,
        )
    )
    db.commit()
    db.refresh(position)
    return _position_out(position)


def _record_assignment(db: Session, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    position = _find_position(db, user_id, payload)
    position.status = "assigned"
    position.current_price = None
    position.alert_target_price = None

    existing_call_alert = db.scalar(
        select(OptionStrategyAlertEvent).where(
            OptionStrategyAlertEvent.user_id == user_id,
            OptionStrategyAlertEvent.position_id == position.id,
            OptionStrategyAlertEvent.kind == "covered_call_candidate",
        )
    )
    if not existing_call_alert:
        db.add(
            OptionStrategyAlertEvent(
                user_id=user_id,
                position_id=position.id,
                symbol=position.symbol,
                kind="covered_call_candidate",
                status="open",
                message=f"{position.symbol} assignment recorded; review covered-call candidates against the shares.",
                target_price=None,
                current_price=None,
            )
        )
    db.commit()
    db.refresh(position)
    return _position_out(position)


def _record_closed(db: Session, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    position = _find_position(db, user_id, payload)
    position.status = "closed"
    db.commit()
    db.refresh(position)
    return _position_out(position)


def roll_review_candidate(position: OptionStrategyWheelPosition | dict[str, Any], as_of: date | None = None, next_cycle_credit: float | None = None) -> dict[str, Any]:
    review_date = as_of or date.today()
    expiration = _parse_date(position.get("expiration") if isinstance(position, dict) else position.expiration)
    current_price = float(position.get("current_price") if isinstance(position, dict) else position.current_price or 0)
    status = str(position.get("status") if isinstance(position, dict) else position.status)
    dte = (expiration - review_date).days
    net_credit = (float(next_cycle_credit) - current_price) if next_cycle_credit is not None else None
    eligible = status == "put_open" and 0 <= dte <= 14 and net_credit is not None and net_credit > 0
    return {
        "eligible": eligible,
        "dte": dte,
        "net_credit": round(net_credit, 2) if net_credit is not None else None,
        "reason": "under 14 DTE with net credit available" if eligible else "roll review requires put_open status, under 14 DTE, and positive net credit",
    }


def _find_position(db: Session, user_id: int, payload: dict[str, Any]) -> OptionStrategyWheelPosition:
    position_id = _optional_int(payload.get("position_id"))
    if position_id is None and isinstance(payload.get("position"), dict):
        position_id = _optional_int(payload["position"].get("id"))
    if position_id is None:
        raise ValueError("Position id is required.")
    position = db.scalar(
        select(OptionStrategyWheelPosition).where(
            OptionStrategyWheelPosition.user_id == user_id,
            OptionStrategyWheelPosition.id == position_id,
        )
    )
    if position is None:
        raise ValueError("Position not found.")
    return position


def _get_or_create_config(db: Session, user_id: int) -> OptionStrategyConfigState:
    row = db.scalar(select(OptionStrategyConfigState).where(OptionStrategyConfigState.user_id == user_id))
    if row:
        tickers = [normalize_symbol(str(symbol)) for symbol in _json_list(row.tickers_json, [])]
        ticker_set = {symbol for symbol in tickers if symbol}
        if ticker_set in (set(LEGACY_DEFAULT_TICKERS), set(_default_tickers(include_leveraged=False))):
            row.tickers_json = json.dumps(_default_tickers())
            row.dte_min = 30
            row.dte_max = 45
            row.rsi_max = 65
            row.min_iv = 0.15
            db.commit()
            db.refresh(row)
        return row
    row = OptionStrategyConfigState(user_id=user_id)
    row.tickers_json = json.dumps(_default_tickers())
    row.dte_min = 30
    row.dte_max = 45
    row.rsi_max = 65
    row.min_iv = 0.15
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _config_out(row: OptionStrategyConfigState) -> dict[str, Any]:
    tickers = [normalize_symbol(str(symbol)) for symbol in _json_list(row.tickers_json, _default_tickers())]
    tickers = [symbol for symbol in tickers if symbol]
    ema_periods = [int(period) for period in _json_list(row.ema_periods_json, DEFAULT_EMA_PERIODS)]
    return {
        "tickers": tickers or _default_tickers(),
        "universe_groups": DEFAULT_UNIVERSE_GROUPS,
        "scan_cadence": "daily",
        "account_value": row.account_value,
        "exposure_cap": row.exposure_cap,
        "dte_min": row.dte_min,
        "dte_max": row.dte_max,
        "rsi_period": row.rsi_period,
        "rsi_max": row.rsi_max,
        "ema_periods": ema_periods[:4] or DEFAULT_EMA_PERIODS,
        "min_iv": row.min_iv,
        "min_iv_rank": DEFAULT_MIN_IV_RANK,
        "min_premium_yield": row.min_premium_yield,
        "target_delta_min": DEFAULT_TARGET_DELTA_MIN,
        "target_delta_max": DEFAULT_TARGET_DELTA_MAX,
        "bb_percent_max": DEFAULT_BB_PERCENT_MAX,
        "earnings_exclusion_days": DEFAULT_EARNINGS_EXCLUSION_DAYS,
        "min_open_interest": DEFAULT_MIN_OPEN_INTEREST,
        "max_spread_pct": DEFAULT_MAX_SPREAD_PCT,
        "profit_take_pct": DEFAULT_PROFIT_TAKE_PCT,
        "single_name_cap": DEFAULT_SINGLE_NAME_CAP,
        "sector_cap": DEFAULT_SECTOR_CAP,
        "webhook_url": row.webhook_url,
        "updated_at": row.updated_at,
    }


def _safe_market_history(db: Session, symbol: str, start_date: date, end_date: date) -> MarketHistory:
    try:
        history = get_market_history(db, symbol, start_date, end_date, force_refresh=False)
    except Exception as exc:
        return _empty_market_history(symbol, start_date, end_date, f"Provider history unavailable for scan: {exc}")
    provider_bars = [bar for bar in history.bars if bar.source != "deterministic offline fallback"]
    if len(provider_bars) >= 60:
        return history
    warnings = ["Insufficient provider history for scanner; skipped synthetic price-history fallback."]
    warnings.extend(history.warnings)
    return _empty_market_history(symbol, start_date, end_date, "; ".join(_dedupe(warnings)))


def _build_symbol_candidates(db: Session, user_id: int, config: dict[str, Any], history: MarketHistory) -> list[dict[str, Any]]:
    symbol = normalize_symbol(history.symbol)
    bars = history.bars
    closes = [float(bar.adjusted_close or bar.close) for bar in bars if float(bar.adjusted_close or bar.close) > 0]
    if len(closes) < 60:
        return []

    ema_periods = config["ema_periods"][:4] if len(config["ema_periods"]) >= 4 else DEFAULT_EMA_PERIODS
    ema8, ema21, ema34, ema55 = [_ema(closes, period) for period in ema_periods]
    latest_close = round(closes[-1], 2)
    previous_close = closes[-2] if len(closes) >= 2 else latest_close
    rsi_value = _rsi(closes, int(config["rsi_period"]))
    bb_percent = _bollinger_percent(closes)
    market_state = {
        "ema_green": bool(ema8[-1] > ema21[-1] and ema34[-1] > ema55[-1]),
        "ema_summary": f"{ema8[-1]:.2f} / {ema21[-1]:.2f}; {ema34[-1]:.2f} / {ema55[-1]:.2f}",
        "rsi": rsi_value,
        "red_day": latest_close < previous_close,
        "bb_percent": bb_percent,
    }

    existing_exposure = _open_symbol_exposure(db, user_id, symbol)
    sector_exposure = _open_sector_exposure(db, user_id, _sector_for_symbol(symbol))
    account_value = max(float(config["account_value"]), 1)
    today = date.today()
    earnings_date = _fetch_yfinance_earnings_date(symbol, today)
    earnings_days = (earnings_date - today).days if earnings_date else None
    contracts = _fetch_yfinance_put_contracts(symbol, latest_close, config, today)
    if not contracts:
        contracts = _fallback_put_contracts(symbol, latest_close, config, today)

    candidates: list[dict[str, Any]] = []
    iv_values = [contract.iv for contract in contracts if contract.iv > 0]
    for contract in contracts:
        delta = _put_delta(latest_close, contract.strike, contract.dte, contract.iv)
        premium_yield = round(contract.mid / contract.strike if contract.strike else 0, 4)
        collateral = round(contract.strike * 100, 2)
        exposure_usage = round((existing_exposure + collateral) / account_value, 4)
        sector_exposure_usage = round((sector_exposure + collateral) / account_value, 4)
        candidate = _candidate_from_checks(
            symbol=symbol,
            config=config,
            market_state=market_state,
            latest_close=latest_close,
            strike=contract.strike,
            expiration=contract.expiration,
            dte=contract.dte,
            delta=round(delta, 3),
            iv=contract.iv,
            iv_rank=_iv_rank_proxy(contract.iv, symbol, iv_values),
            bid=contract.bid,
            ask=contract.ask,
            mid=contract.mid,
            open_interest=contract.open_interest,
            premium_yield=premium_yield,
            collateral=collateral,
            exposure_usage=exposure_usage,
            sector_exposure_usage=sector_exposure_usage,
            earnings_date=earnings_date,
            earnings_days=earnings_days,
            provider=contract.provider,
        )
        candidates.append(candidate)
    return candidates


def _candidate_from_checks(
    *,
    symbol: str,
    config: dict[str, Any],
    market_state: dict[str, Any],
    latest_close: float,
    strike: float,
    expiration: date,
    dte: int,
    delta: float,
    iv: float,
    iv_rank: float,
    bid: float,
    ask: float,
    mid: float,
    open_interest: int,
    premium_yield: float,
    collateral: float,
    exposure_usage: float,
    sector_exposure_usage: float,
    earnings_date: date | None,
    earnings_days: int | None,
    provider: str,
) -> dict[str, Any]:
    spread_ratio = (ask - bid) / mid if mid > 0 else math.inf
    ema_support = bool(market_state["ema_green"])
    rsi = float(market_state["rsi"])
    bb_percent = float(market_state["bb_percent"])
    rsi_pass = rsi <= float(config["rsi_max"])
    bb_pass = bb_percent <= float(config["bb_percent_max"])
    iv_pass = iv >= float(config["min_iv"])
    iv_rank_pass = iv_rank >= float(config["min_iv_rank"])
    earnings_pass = earnings_days is None or earnings_days > int(config["earnings_exclusion_days"])
    exposure_pass = exposure_usage <= float(config["exposure_cap"])
    single_name_pass = exposure_usage <= float(config["single_name_cap"])
    sector_pass = sector_exposure_usage <= float(config["sector_cap"])
    yield_pass = premium_yield >= float(config["min_premium_yield"])
    liquidity_pass = (
        int(config["dte_min"]) <= dte <= int(config["dte_max"])
        and float(config["target_delta_min"]) <= abs(delta) <= float(config["target_delta_max"])
        and open_interest >= int(config["min_open_interest"])
        and bid > 0
        and spread_ratio <= float(config["max_spread_pct"])
    )
    score = _score_candidate(
        premium_yield=premium_yield,
        iv_rank=iv_rank,
        rsi=rsi,
        bb_percent=bb_percent,
        spread_ratio=spread_ratio,
        open_interest=open_interest,
        ema_support=ema_support,
        red_day=bool(market_state["red_day"]),
    )
    checks = [
        _check("ema_cloud", "EMA cloud", True, market_state["ema_summary"], "Context only", "Trend cloud supports the candidate." if ema_support else "Trend cloud is defensive; review chart context."),
        _check("rsi", "RSI 14", rsi_pass, round(rsi, 1), f"<= {config['rsi_max']}", "RSI is not overbought." if rsi_pass else "RSI is above the entry ceiling."),
        _check("bb_percent", "Bollinger Band %", bb_pass, round(bb_percent, 3), f"<= {config['bb_percent_max']}", "Price is not extended into the upper band." if bb_pass else "Price is too close to the upper band."),
        _check("iv", "Contract IV", iv_pass, _pct(iv), f">= {_pct(config['min_iv'])}", f"{_pct(iv)} implied volatility."),
        _check("iv_rank", "IV rank proxy", iv_rank_pass, _pct(iv_rank), f">= {_pct(config['min_iv_rank'])}", "Premium regime is rich enough to review." if iv_rank_pass else "Premium regime is not rich enough."),
        _check("earnings", "Earnings window", earnings_pass, _format_earnings(earnings_date, earnings_days), f"> {config['earnings_exclusion_days']} days or unknown", "No known near-term earnings event." if earnings_pass else "Known earnings are inside the exclusion window."),
        _check("red_day", "Underlying red", True, "Red" if market_state["red_day"] else "Green", "Context only", "Underlying is down on the latest completed candle." if market_state["red_day"] else "Underlying is not red; use as review context only."),
        _check("exposure", "Ticker exposure", exposure_pass, _pct(exposure_usage), f"<= {_pct(config['exposure_cap'])}", "Collateral fits within exposure cap." if exposure_pass else "New collateral would exceed the configured exposure cap."),
        _check("single_name", "Single-name cap", single_name_pass, _pct(exposure_usage), f"<= {_pct(config['single_name_cap'])}", "Single-name sizing is within wheel guardrails." if single_name_pass else "Single-name allocation would exceed the wheel guardrail."),
        _check("sector", "Sector cap", sector_pass, _pct(sector_exposure_usage), f"<= {_pct(config['sector_cap'])}", "Sector sizing is within wheel guardrails." if sector_pass else "Sector allocation would exceed the wheel guardrail."),
        _check("yield", "Premium yield", yield_pass, _pct(premium_yield), f">= {_pct(config['min_premium_yield'])}", f"{_pct(premium_yield)} premium over strike collateral."),
        _check(
            "liquidity",
            "DTE / delta / liquidity",
            liquidity_pass,
            f"{dte} DTE, {delta:.2f} delta, {_pct(spread_ratio)} spread, OI {open_interest}",
            f"{config['dte_min']}-{config['dte_max']} DTE, {config['target_delta_min']:.2f}-{config['target_delta_max']:.2f} delta, tight spread, OI >= {config['min_open_interest']}",
            "DTE, delta, spread, and open interest are in range." if liquidity_pass else "One or more contract-selection filters failed.",
        ),
        _check("provider", "Provider", provider == "yfinance", provider, "yfinance", "Live option chain." if provider == "yfinance" else "Fallback contract estimate; verify manually."),
    ]
    blocked_reasons = [
        f"RSI above {config['rsi_max']}" if not rsi_pass else "",
        f"Bollinger Band % above {_pct(config['bb_percent_max'])}" if not bb_pass else "",
        f"IV below {_pct(config['min_iv'])}" if not iv_pass else "",
        f"IV rank proxy below {_pct(config['min_iv_rank'])}" if not iv_rank_pass else "",
        f"Earnings inside {config['earnings_exclusion_days']} days" if not earnings_pass else "",
        f"Exposure cap would exceed {_pct(config['exposure_cap'])}" if not exposure_pass else "",
        f"Single-name cap would exceed {_pct(config['single_name_cap'])}" if not single_name_pass else "",
        f"Sector cap would exceed {_pct(config['sector_cap'])}" if not sector_pass else "",
        f"Premium yield below {_pct(config['min_premium_yield'])}" if not yield_pass else "",
        "DTE/delta/liquidity filter failed" if not liquidity_pass else "",
        "Live option chain unavailable" if provider != "yfinance" else "",
    ]
    blocked_reasons = [reason for reason in blocked_reasons if reason]
    return {
        "symbol": symbol,
        "action": "sell_put",
        "status": "approved" if not blocked_reasons else "blocked",
        "sector": _sector_for_symbol(symbol),
        "underlying_price": latest_close,
        "strike": strike,
        "expiration": expiration,
        "dte": dte,
        "delta": delta,
        "iv": iv,
        "iv_rank": iv_rank,
        "bb_percent": bb_percent,
        "earnings_date": earnings_date,
        "earnings_days": earnings_days,
        "spread_pct": spread_ratio,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "open_interest": open_interest,
        "premium_yield": premium_yield,
        "collateral": collateral,
        "alert_target_price": round(mid * (1 - float(config["profit_take_pct"])), 2),
        "exposure_usage": exposure_usage,
        "score": score,
        "if_expires_return": premium_yield,
        "if_assigned_basis": round(strike - mid, 2),
        "provider": provider,
        "checklist": checks,
        "blocked_reasons": blocked_reasons,
    }


def _scan_result_out(scan_run: OptionStrategyScanRun, rows: list[OptionStrategySignalCandidate]) -> dict[str, Any]:
    return {
        "scan_run_id": scan_run.id,
        "scanned_at": scan_run.scanned_at,
        "data_source": scan_run.data_source,
        "signals": [_signal_out(row) for row in rows],
        "warnings": _json_list(scan_run.warnings_json, []),
    }


def _signal_out(row: OptionStrategySignalCandidate) -> dict[str, Any]:
    checklist = _json_list(row.checklist_json, [])
    spread_pct = (row.ask - row.bid) / row.mid if row.mid else None
    bb_percent = _check_actual_float(checklist, "bb_percent")
    iv_rank = _check_actual_pct(checklist, "iv_rank")
    earnings_value = _check_actual_string(checklist, "earnings")
    earnings_date, earnings_days = _parse_earnings_value(earnings_value)
    provider = _check_actual_string(checklist, "provider") or _scan_provider(row)
    score = _score_from_row(row, checklist, spread_pct)
    deep_dive_rank = row.rank if row.rank <= 5 else None
    return {
        "id": row.id,
        "symbol": row.symbol,
        "action": row.action,
        "status": row.status,
        "sector": _sector_for_symbol(row.symbol),
        "underlying_price": row.underlying_price,
        "strike": row.strike,
        "expiration": row.expiration,
        "dte": row.dte,
        "delta": row.delta,
        "iv": row.iv,
        "iv_rank": iv_rank,
        "bb_percent": bb_percent,
        "earnings_date": earnings_date,
        "earnings_days": earnings_days,
        "spread_pct": spread_pct,
        "bid": row.bid,
        "ask": row.ask,
        "mid": row.mid,
        "open_interest": row.open_interest,
        "premium_yield": row.premium_yield,
        "collateral": row.collateral,
        "alert_target_price": row.alert_target_price,
        "exposure_usage": row.exposure_usage,
        "score": score,
        "deep_dive_rank": deep_dive_rank,
        "deep_dive_summary": _deep_dive_summary_from_row(row, checklist, deep_dive_rank),
        "if_expires_return": row.premium_yield,
        "if_assigned_basis": round(row.strike - row.mid, 2),
        "provider": provider,
        "checklist": checklist,
        "blocked_reasons": _json_list(row.blocked_reasons_json, []),
        "created_at": row.created_at,
    }


def _position_out(row: OptionStrategyWheelPosition) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "status": row.status,
        "option_type": row.option_type,
        "strike": row.strike,
        "expiration": row.expiration,
        "contracts": row.contracts,
        "entry_premium": row.entry_premium,
        "current_price": row.current_price,
        "alert_target_price": row.alert_target_price,
        "collateral": row.collateral,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _alert_out(row: OptionStrategyAlertEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "kind": row.kind,
        "status": row.status,
        "message": row.message,
        "target_price": row.target_price,
        "current_price": row.current_price,
        "created_at": row.created_at,
    }


def _candidate_payload_from_row(row: OptionStrategySignalCandidate | None) -> dict[str, Any]:
    if row is None:
        return {}
    return _signal_out(row)


def _latest_scan_run(db: Session, user_id: int) -> OptionStrategyScanRun | None:
    return db.scalar(
        select(OptionStrategyScanRun)
        .where(OptionStrategyScanRun.user_id == user_id)
        .order_by(desc(OptionStrategyScanRun.scanned_at), desc(OptionStrategyScanRun.id))
    )


def _market_date_today() -> date:
    return datetime.now(US_MARKET_TIME_ZONE).date()


def _latest_scan_run_for_date(db: Session, user_id: int, scan_date: date) -> OptionStrategyScanRun | None:
    start, end = _utc_bounds_for_market_date(scan_date)
    return db.scalar(
        select(OptionStrategyScanRun)
        .where(
            OptionStrategyScanRun.user_id == user_id,
            OptionStrategyScanRun.scanned_at >= start,
            OptionStrategyScanRun.scanned_at < end,
        )
        .order_by(desc(OptionStrategyScanRun.scanned_at), desc(OptionStrategyScanRun.id))
    )


def _utc_bounds_for_market_date(scan_date: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(scan_date, time.min, tzinfo=US_MARKET_TIME_ZONE)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )


def _open_symbol_exposure(db: Session, user_id: int, symbol: str) -> float:
    rows = db.scalars(
        select(OptionStrategyWheelPosition).where(
            OptionStrategyWheelPosition.user_id == user_id,
            OptionStrategyWheelPosition.symbol == symbol,
            OptionStrategyWheelPosition.status != "closed",
        )
    ).all()
    return sum(float(row.collateral or row.strike * row.contracts * 100) for row in rows)


def _open_sector_exposure(db: Session, user_id: int, sector: str) -> float:
    rows = db.scalars(
        select(OptionStrategyWheelPosition).where(
            OptionStrategyWheelPosition.user_id == user_id,
            OptionStrategyWheelPosition.status != "closed",
        )
    ).all()
    return sum(
        float(row.collateral or row.strike * row.contracts * 100)
        for row in rows
        if _sector_for_symbol(row.symbol) == sector
    )


def _default_tickers(*, include_leveraged: bool = True) -> list[str]:
    return [item.symbol for item in _default_universe_items(include_leveraged=include_leveraged)]


def _default_universe_items(*, include_leveraged: bool = True) -> list[UniverseItem]:
    seen: set[str] = set()
    items: list[UniverseItem] = []

    def add(symbol: str, name: str, sector: str, group: str) -> None:
        normalized = normalize_symbol(symbol)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        items.append(UniverseItem(symbol=normalized, name=name, sector=sector or "Unknown", group=group))

    for holding in INDEX_DEFINITIONS["SPY"].holdings[:30]:
        add(str(holding["symbol"]), str(holding["name"]), str(holding.get("sector") or ""), "S&P 500 top 30")
    for holding in INDEX_DEFINITIONS["QTOP"].holdings[:30]:
        add(str(holding["symbol"]), str(holding["name"]), str(holding.get("sector") or ""), "Nasdaq top 30")
    etf_names = {
        "QQQ": ("Invesco QQQ Trust", "ETF"),
        "SPY": ("SPDR S&P 500 ETF Trust", "ETF"),
        "SMH": ("VanEck Semiconductor ETF", "ETF"),
        "XLE": ("Energy Select Sector SPDR Fund", "ETF"),
        "XLI": ("Industrial Select Sector SPDR Fund", "ETF"),
        "UPRO": ("ProShares UltraPro S&P500", "Leveraged ETF"),
        "TQQQ": ("ProShares UltraPro QQQ", "Leveraged ETF"),
        "SOXL": ("Direxion Daily Semiconductor Bull 3X Shares", "Leveraged ETF"),
    }
    extra_tickers = DEFAULT_EXTRA_TICKERS if include_leveraged else DEFAULT_CORE_TICKERS
    for symbol in extra_tickers:
        name, sector = etf_names[symbol]
        group = "Leveraged ETFs" if symbol in DEFAULT_LEVERAGED_TICKERS else "Core ETFs"
        add(symbol, name, sector, group)
    return items


def _sector_for_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized in DEFAULT_CORE_TICKERS:
        return "ETF"
    if normalized in DEFAULT_LEVERAGED_TICKERS:
        return "Leveraged ETF"
    for definition in INDEX_DEFINITIONS.values():
        for holding in definition.holdings:
            if normalize_symbol(str(holding["symbol"])) == normalized:
                return str(holding.get("sector") or "Unknown")
    return "Unknown"


def _fetch_yfinance_put_contracts(symbol: str, latest_close: float, config: dict[str, Any], today: date) -> list[PutContract]:
    try:
        import yfinance as yf
    except Exception:
        return []
    try:
        ticker = yf.Ticker(symbol.replace(".", "-"))
        expirations = [
            date.fromisoformat(value)
            for value in getattr(ticker, "options", [])
            if _is_iso_date(value)
        ]
    except Exception:
        return []

    contracts: list[PutContract] = []
    for expiration in expirations:
        dte = (expiration - today).days
        if not int(config["dte_min"]) <= dte <= int(config["dte_max"]):
            continue
        try:
            chain = ticker.option_chain(expiration.isoformat())
            rows = chain.puts.to_dict("records")
        except Exception:
            continue
        for row in rows:
            contract = _put_contract_from_yfinance_row(row, expiration, dte)
            if not contract or contract.strike >= latest_close:
                continue
            contracts.append(contract)

    contracts.sort(
        key=lambda item: (
            abs(abs(_put_delta(latest_close, item.strike, item.dte, item.iv)) - 0.30),
            -item.mid,
            item.expiration,
        )
    )
    return contracts[:6]


def _put_contract_from_yfinance_row(row: dict[str, Any], expiration: date, dte: int) -> PutContract | None:
    strike = _safe_float(row.get("strike"))
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    last_price = _safe_float(row.get("lastPrice"))
    iv = _safe_float(row.get("impliedVolatility"))
    open_interest = int(_safe_float(row.get("openInterest")) or 0)
    volume_value = _safe_float(row.get("volume"))
    if strike <= 0:
        return None
    if bid <= 0 and ask <= 0 and last_price <= 0:
        return None
    if bid <= 0 or ask <= 0:
        mid = last_price
        bid = bid or max(0.01, mid * 0.94)
        ask = ask or max(bid + 0.01, mid * 1.06)
    else:
        mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return PutContract(
        strike=round(strike, 2),
        expiration=expiration,
        dte=dte,
        bid=round(bid, 2),
        ask=round(ask, 2),
        mid=round(mid, 2),
        iv=round(max(iv, 0.01), 4),
        open_interest=open_interest,
        volume=int(volume_value) if volume_value else None,
        provider="yfinance",
    )


def _fallback_put_contracts(symbol: str, latest_close: float, config: dict[str, Any], today: date) -> list[PutContract]:
    base_iv = _BASE_IV.get(symbol, 0.45)
    base_yield = _BASE_YIELD.get(symbol, 0.048)
    steps = [
        (30, 0.22, -0.006),
        (34, 0.26, 0.000),
        (38, 0.30, 0.005),
        (42, 0.34, 0.009),
        (45, 0.36, 0.012),
    ]
    contracts: list[PutContract] = []
    for index, (target_dte, delta_abs, yield_adjustment) in enumerate(steps):
        expiration = _next_friday(today + timedelta(days=target_dte))
        dte = (expiration - today).days
        if not int(config["dte_min"]) <= dte <= int(config["dte_max"]):
            continue
        strike = _round_strike(latest_close * _strike_factor(symbol, delta_abs), latest_close)
        iv = round(max(0.18, base_iv + (delta_abs - 0.26) * 0.20), 4)
        premium_yield = max(0.012, base_yield + yield_adjustment)
        mid = round(max(0.15, strike * premium_yield), 2)
        spread_pct = 0.08 + index * 0.012
        bid = round(max(0.05, mid * (1 - spread_pct / 2)), 2)
        ask = round(max(bid + 0.01, mid * (1 + spread_pct / 2)), 2)
        contracts.append(
            PutContract(
                strike=strike,
                expiration=expiration,
                dte=dte,
                bid=bid,
                ask=ask,
                mid=mid,
                iv=iv,
                open_interest=220 + (index + 1) * 120 + _stable_symbol_offset(symbol),
                volume=None,
                provider="deterministic fallback",
            )
        )
    return contracts


def _fetch_yfinance_earnings_date(symbol: str, today: date) -> date | None:
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol.replace(".", "-"))
        calendar = ticker.get_calendar()
    except Exception:
        return None
    if not isinstance(calendar, dict):
        return None
    for key in ("Earnings Date", "Earnings High", "Earnings Low"):
        raw = calendar.get(key)
        parsed = _coerce_date(raw)
        if parsed and parsed >= today:
            return parsed
    return None


def _synthetic_market_history(symbol: str, start_date: date, end_date: date, warning: str) -> MarketHistory:
    normalized = normalize_symbol(symbol)
    bars: list[MarketHistoryBar] = []
    current = start_date
    price = _SYNTHETIC_BASE_PRICE.get(normalized, 100.0) * (0.82 + (_stable_symbol_offset(normalized) % 9) / 100)
    trading_day = 0
    while current <= end_date:
        if current.weekday() < 5:
            wave = math.sin(trading_day / 11 + _stable_symbol_offset(normalized)) * 0.012
            pulse = math.cos(trading_day / 29) * 0.008
            drift = 0.00075 if normalized in {"QQQ", "SPY", "SMH"} else 0.0011
            if (end_date - current).days <= 4:
                drift -= 0.013
            price = max(4.0, price * (1 + drift + wave + pulse))
            bars.append(MarketHistoryBar(date=current, close=round(price, 4), adjusted_close=round(price, 4), dividend=0, source="synthetic scan fallback"))
            trading_day += 1
        current += timedelta(days=1)
    return MarketHistory(
        symbol=normalized,
        name=f"{normalized} option strategy fallback history",
        benchmark=normalized,
        category="Option strategy universe",
        requested_start_date=start_date,
        requested_end_date=end_date,
        start_date=bars[0].date if bars else None,
        end_date=bars[-1].date if bars else None,
        bars=bars,
        warnings=[warning],
    )


def _empty_market_history(symbol: str, start_date: date, end_date: date, warning: str) -> MarketHistory:
    normalized = normalize_symbol(symbol)
    return MarketHistory(
        symbol=normalized,
        name=f"{normalized} option strategy history",
        benchmark=normalized,
        category="Option strategy universe",
        requested_start_date=start_date,
        requested_end_date=end_date,
        start_date=None,
        end_date=None,
        bars=[],
        warnings=[warning],
    )


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    current = values[0]
    result = [current]
    for value in values[1:]:
        current = (value - current) * multiplier + current
        result.append(current)
    return result


def _rsi(values: list[float], period: int) -> float:
    if len(values) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0)
        loss = abs(min(change, 0))
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return round(100 - (100 / (1 + relative_strength)), 2)


def _bollinger_percent(values: list[float], period: int = 20) -> float:
    if len(values) < period:
        return 0.5
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((value - mean) ** 2 for value in window) / period
    band_width = 4 * math.sqrt(variance)
    if band_width <= 0:
        return 0.5
    lower = mean - 2 * math.sqrt(variance)
    return round(min(max((values[-1] - lower) / band_width, 0), 1), 4)


def _put_delta(underlying: float, strike: float, dte: int, iv: float) -> float:
    if underlying <= 0 or strike <= 0 or dte <= 0 or iv <= 0:
        return -0.30
    t = dte / 365
    denominator = iv * math.sqrt(t)
    if denominator <= 0:
        return -0.30
    d1 = (math.log(underlying / strike) + (RISK_FREE_RATE + (iv * iv) / 2) * t) / denominator
    return round(_normal_cdf(d1) - 1, 4)


def _normal_cdf(value: float) -> float:
    return (1 + math.erf(value / math.sqrt(2))) / 2


def _iv_rank_proxy(iv: float, symbol: str, chain_ivs: list[float]) -> float:
    usable = [value for value in chain_ivs if value > 0]
    if len(usable) >= 3:
        low = min(usable)
        high = max(usable)
        if high > low:
            return round(min(max((iv - low) / (high - low), 0), 1), 4)
    base = _BASE_IV.get(symbol, 0.45)
    low = max(0.12, base * 0.55)
    high = max(low + 0.05, base * 1.45)
    return round(min(max((iv - low) / (high - low), 0), 1), 4)


def _score_candidate(
    *,
    premium_yield: float,
    iv_rank: float,
    rsi: float,
    bb_percent: float,
    spread_ratio: float,
    open_interest: int,
    ema_support: bool,
    red_day: bool,
) -> float:
    score = 0.0
    score += min(premium_yield / 0.08, 1.5) * 28
    score += min(iv_rank, 1) * 22
    score += max(0, (70 - rsi) / 70) * 16
    score += max(0, (0.85 - bb_percent) / 0.85) * 14
    score += max(0, (0.20 - min(spread_ratio, 0.20)) / 0.20) * 10
    score += min(open_interest / 1000, 1) * 6
    score += 2 if ema_support else 0
    score += 2 if red_day else 0
    return round(score, 1)


def _score_from_row(row: OptionStrategySignalCandidate, checklist: list[Any], spread_pct: float | None) -> float:
    iv_rank = _check_actual_pct(checklist, "iv_rank") or 0
    bb_percent = _check_actual_float(checklist, "bb_percent") or 0.5
    rsi = _check_actual_float(checklist, "rsi") or 50
    return _score_candidate(
        premium_yield=row.premium_yield,
        iv_rank=iv_rank,
        rsi=rsi,
        bb_percent=bb_percent,
        spread_ratio=spread_pct if spread_pct is not None else 0.15,
        open_interest=row.open_interest,
        ema_support=bool(_check_passed(checklist, "ema_cloud")),
        red_day=str(_check_actual_string(checklist, "red_day") or "").lower() == "red",
    )


def _round_strike(target: float, underlying: float) -> float:
    increment = 5 if underlying >= 200 else 1
    strike = round(target / increment) * increment
    if strike >= underlying:
        strike -= increment
    return round(max(increment, strike), 2)


def _strike_factor(symbol: str, delta_abs: float) -> float:
    if symbol in {"TQQQ", "SOXL", "UPRO"}:
        return 0.80 + delta_abs * 0.45
    return 0.88 + delta_abs * 0.31


def _next_friday(value: date) -> date:
    days_ahead = (4 - value.weekday()) % 7
    return value + timedelta(days=days_ahead)


def _check(id_: str, label: str, passed: bool, actual: Any, expected: Any, detail: str) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
        "detail": detail,
    }


def _check_for(checklist: list[Any], id_: str) -> dict[str, Any] | None:
    for item in checklist:
        if isinstance(item, dict) and item.get("id") == id_:
            return item
    return None


def _check_passed(checklist: list[Any], id_: str) -> bool:
    item = _check_for(checklist, id_)
    return bool(item and item.get("passed"))


def _check_actual_float(checklist: list[Any], id_: str) -> float | None:
    item = _check_for(checklist, id_)
    if not item:
        return None
    actual = item.get("actual")
    if isinstance(actual, (int, float)):
        return float(actual)
    if isinstance(actual, str):
        try:
            return float(actual.strip().rstrip("%")) / (100 if actual.strip().endswith("%") else 1)
        except ValueError:
            return None
    return None


def _check_actual_pct(checklist: list[Any], id_: str) -> float | None:
    item = _check_for(checklist, id_)
    if not item:
        return None
    actual = item.get("actual")
    if isinstance(actual, (int, float)):
        return float(actual)
    if isinstance(actual, str):
        try:
            stripped = actual.strip()
            return float(stripped.rstrip("%")) / (100 if stripped.endswith("%") else 1)
        except ValueError:
            return None
    return None


def _check_actual_string(checklist: list[Any], id_: str) -> str | None:
    item = _check_for(checklist, id_)
    if not item:
        return None
    actual = item.get("actual")
    return str(actual) if actual not in (None, "") else None


def _format_earnings(earnings_date: date | None, earnings_days: int | None) -> str:
    if not earnings_date:
        return "Unknown"
    return f"{earnings_date.isoformat()} ({earnings_days} days)"


def _parse_earnings_value(value: str | None) -> tuple[date | None, int | None]:
    if not value or value == "Unknown":
        return None, None
    raw_date = value.split(" ", 1)[0]
    try:
        parsed = date.fromisoformat(raw_date)
    except ValueError:
        return None, None
    if "(" not in value:
        return parsed, None
    try:
        days = int(value.split("(", 1)[1].split(" ", 1)[0])
    except (IndexError, ValueError):
        days = None
    return parsed, days


def _scan_provider(row: OptionStrategySignalCandidate) -> str:
    try:
        source = row.scan_run.data_source
    except Exception:
        source = ""
    if "yfinance" in source and "fallback" not in source:
        return "yfinance"
    if "fallback" in source:
        return "deterministic fallback"
    return source or "unknown"


def _deep_dive_summary(candidate: dict[str, Any], rank: int) -> str:
    reasons = []
    if candidate["status"] == "approved":
        reasons.append("approved CSP candidate")
    else:
        reasons.append("blocked candidate worth review only if blockers clear")
    reasons.append(f"{_pct(candidate['premium_yield'])} premium yield")
    reasons.append(f"{_pct(candidate['iv_rank'])} IV-rank proxy")
    reasons.append(f"{candidate['dte']} DTE")
    reasons.append(f"{candidate['delta']:.2f} delta")
    if candidate["blocked_reasons"]:
        reasons.append(f"blocked by {', '.join(candidate['blocked_reasons'][:2])}")
    return f"Research priority {rank}: {candidate['symbol']} is a {', '.join(reasons)}. Review chart trend, upcoming news, and whether you would own shares near the effective basis before acting."


def _deep_dive_summary_from_row(row: OptionStrategySignalCandidate, checklist: list[Any], rank: int | None) -> str:
    rank_label = rank if rank is not None else row.rank
    iv_rank = _check_actual_pct(checklist, "iv_rank")
    blocked = _json_list(row.blocked_reasons_json, [])
    parts = [
        f"{_pct(row.premium_yield)} premium yield",
        f"{row.dte} DTE",
        f"{row.delta:.2f} delta",
    ]
    if iv_rank is not None:
        parts.append(f"{_pct(iv_rank)} IV-rank proxy")
    if blocked:
        parts.append(f"blocked by {', '.join(blocked[:2])}")
    return f"Research priority {rank_label}: {row.symbol} has {', '.join(parts)}. Review the underlying business, chart context, upcoming events, and assignment comfort before any trade decision."


def _pct(value: float) -> str:
    return f"{float(value) * 100:.1f}%"


def _json_list(raw: str | None, fallback: list[Any]) -> list[Any]:
    if not raw:
        return list(fallback)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return list(fallback)
    return value if isinstance(value, list) else list(fallback)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError("Expected ISO date.")


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (list, tuple)) and value:
        return _coerce_date(value[0])
    if hasattr(value, "iloc"):
        try:
            return _coerce_date(value.iloc[0])
        except Exception:
            return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    if hasattr(value, "date"):
        try:
            parsed = value.date()
            return parsed if isinstance(parsed, date) else None
        except Exception:
            return None
    return None


def _safe_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(numeric) or math.isinf(numeric):
        return 0.0
    return numeric


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_symbol_offset(symbol: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(symbol)) % 97
