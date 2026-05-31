"""Portfolio concentration analysis for the Diversification feature.

Pure-math service — no network calls, no database writes.
Takes user-supplied holdings (symbol, weight) and benchmarks against SCHD's
sector profile to produce a concentration score and sector gap table.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.direct_indexing import Holding, normalize_holdings
from app.services.schd_data import get_schd_sector_weights


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SectorGapRow:
    sector: str
    portfolio_weight: float     # user portfolio's allocation to this sector
    index_weight: float         # SCHD's allocation to this sector
    gap: float                  # portfolio_weight − index_weight  (positive = overweight)


@dataclass
class ConcentrationResult:
    hhi: float                          # Herfindahl-Hirschman Index (0–1); lower = more diversified
    diversification_score: int          # 0–100 (100 = perfectly equal-weight vs SCHD)
    top_holding: str                    # symbol with largest weight
    top_holding_weight: float           # weight of that symbol
    sector_weights: dict[str, float]    # user's sector weights
    sector_vs_index: list[SectorGapRow] # per-sector gap table
    active_share: float                 # fraction of holdings not matching SCHD top-25
    concentration_warnings: list[str]   # human-readable warnings


# ── Math helpers ──────────────────────────────────────────────────────────────

def hhi(weights: list[float]) -> float:
    """Herfindahl-Hirschman Index.  Range: 1/N (equal-weight) → 1.0 (all in one stock)."""
    return sum(w * w for w in weights)


def diversification_score(hhi_val: float, n_holdings: int) -> int:
    """Map HHI → 0-100 score relative to perfectly equal-weight (N holdings).

    Score 100 = as diversified as an N-stock equal-weight portfolio.
    Score   0 = 100% in one stock.
    """
    if n_holdings < 1:
        return 0
    min_hhi = 1.0 / n_holdings
    if hhi_val <= min_hhi:
        return 100
    # Normalise: how far from "perfect" are we, scaled by maximum possible HHI range?
    return max(0, int(100 * (1.0 - (hhi_val - min_hhi) / (1.0 - min_hhi))))


def _aggregate_sector_weights(holdings: list[Holding]) -> dict[str, float]:
    """Sum holding weights by sector."""
    out: dict[str, float] = {}
    for h in holdings:
        sector = (h.sector or "Other").strip() or "Other"
        out[sector] = out.get(sector, 0.0) + h.weight
    return out


# ── Main analysis function ────────────────────────────────────────────────────

def analyze_concentration(
    holdings: list[Holding],
    index_symbol: str = "SCHD",   # reserved for future multi-index support
) -> ConcentrationResult:
    """Compute HHI, diversification score, and sector gaps vs SCHD.

    `holdings` must already be weight-normalised (weights sum to 1.0).
    """
    if not holdings:
        return ConcentrationResult(
            hhi=1.0, diversification_score=0,
            top_holding="", top_holding_weight=0.0,
            sector_weights={}, sector_vs_index=[],
            active_share=1.0, concentration_warnings=["No holdings provided."],
        )

    # Normalise in case weights don't sum exactly to 1
    holdings = normalize_holdings(holdings)
    weights  = [h.weight for h in holdings]

    # ── Concentration metrics ─────────────────────────────────────────────────
    hhi_val = hhi(weights)
    score   = diversification_score(hhi_val, len(holdings))

    top = max(holdings, key=lambda h: h.weight)

    # ── Sector analysis ───────────────────────────────────────────────────────
    portfolio_sectors = _aggregate_sector_weights(holdings)
    schd_sectors      = get_schd_sector_weights()
    all_sectors       = sorted(set(portfolio_sectors) | set(schd_sectors))

    sector_gaps = [
        SectorGapRow(
            sector=s,
            portfolio_weight=round(portfolio_sectors.get(s, 0.0), 4),
            index_weight=round(schd_sectors.get(s, 0.0), 4),
            gap=round(portfolio_sectors.get(s, 0.0) - schd_sectors.get(s, 0.0), 4),
        )
        for s in all_sectors
    ]
    # Sort by absolute gap descending (biggest mismatches first)
    sector_gaps.sort(key=lambda r: abs(r.gap), reverse=True)

    # ── Active share: fraction of weights NOT in SCHD top-25 ─────────────────
    from app.services.schd_data import get_schd_symbols
    schd_syms   = set(get_schd_symbols())
    in_schd_wt  = sum(h.weight for h in holdings if h.symbol in schd_syms)
    active_share = round(1.0 - in_schd_wt, 4)

    # ── Concentration warnings ────────────────────────────────────────────────
    warnings: list[str] = []
    if top.weight >= 0.50:
        warnings.append(
            f"{top.symbol} makes up {top.weight*100:.0f}% of your portfolio — extremely concentrated."
        )
    elif top.weight >= 0.25:
        warnings.append(
            f"{top.symbol} makes up {top.weight*100:.0f}% of your portfolio — highly concentrated."
        )
    if hhi_val > 0.25:
        warnings.append(
            f"HHI of {hhi_val:.3f} indicates a highly concentrated portfolio "
            f"(below 0.15 is considered moderately diversified)."
        )
    overweight = [g for g in sector_gaps if g.gap > 0.15]
    for g in overweight[:2]:
        warnings.append(
            f"{g.sector} is {g.gap*100:.0f} percentage points overweight vs SCHD "
            f"({g.portfolio_weight*100:.0f}% vs {g.index_weight*100:.0f}%)."
        )

    return ConcentrationResult(
        hhi=round(hhi_val, 4),
        diversification_score=score,
        top_holding=top.symbol,
        top_holding_weight=round(top.weight, 4),
        sector_weights={k: round(v, 4) for k, v in portfolio_sectors.items()},
        sector_vs_index=sector_gaps,
        active_share=active_share,
        concentration_warnings=warnings,
    )
