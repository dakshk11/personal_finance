from dataclasses import dataclass


DEFAULT_DIRECT_INDEX_MODEL = "risk_score"
EXECUTABLE_DIRECT_INDEX_MODELS = ("risk_score", "threshold_throttle", "peer_basket", "completion_etf")


@dataclass(frozen=True)
class DirectIndexModel:
    id: str
    label: str
    rank: int
    executable: bool
    summary: str
    best_for: str
    source_support: list[str]
    replacement_strategy: str = "completion_etf"
    tracking_budget_multiplier: float = 1.0
    min_loss_percent: float | None = None
    min_loss_dollars: float | None = None
    min_harvest_loss_dollars: float | None = None
    scan_interval_days: int | None = None


EXECUTABLE_MODELS: dict[str, DirectIndexModel] = {
    "risk_score": DirectIndexModel(
        id="risk_score",
        label="Risk-score optimizer",
        rank=1,
        executable=True,
        summary="Scores tax-loss value against tracking drift, turnover, and wash-sale constraints.",
        best_for="Default model when tracking discipline dominates tax value.",
        source_support=["Frec scoring function", "Wealthfront tax alpha minus tracking error", "IRS wash-sale baseline"],
        replacement_strategy="completion_etf",
    ),
    "threshold_throttle": DirectIndexModel(
        id="threshold_throttle",
        label="Threshold throttle",
        rank=2,
        executable=True,
        summary="Harvests only larger losses and throttles active risk, following the Israelov/Lu threshold framework.",
        best_for="Lower-turnover accounts where preserving tracking matters more than maximizing harvested losses.",
        source_support=["Israelov/Lu optimized TLH thresholds", "IRS wash-sale baseline"],
        replacement_strategy="peer_basket",
        tracking_budget_multiplier=0.35,
        min_loss_percent=0.02,
        min_loss_dollars=25.0,
        min_harvest_loss_dollars=25.0,
        scan_interval_days=7,
    ),
    "peer_basket": DirectIndexModel(
        id="peer_basket",
        label="Peer basket",
        rank=3,
        executable=True,
        summary="Replaces harvested names with same-sector/top-weight peer baskets instead of an ETF sleeve.",
        best_for="Accounts that prefer stock-only replacement exposure and can tolerate more rows per harvest.",
        source_support=["Frec replacement allocation discussion", "Wealthfront correlated replacement examples"],
        replacement_strategy="peer_basket",
        tracking_budget_multiplier=0.50,
    ),
    "completion_etf": DirectIndexModel(
        id="completion_etf",
        label="Completion ETF sleeve",
        rank=4,
        executable=True,
        summary="Uses the selected ETF/index sleeve as a temporary replacement during wash-sale lockout.",
        best_for="Operational simplicity and lower replacement trade count.",
        source_support=["Wealthfront completion ETF approach", "ETF-pair TLH baseline"],
        replacement_strategy="completion_etf",
        tracking_budget_multiplier=0.90,
    ),
}


RESEARCH_ONLY_MODELS: tuple[DirectIndexModel, ...] = (
    DirectIndexModel(
        id="etf_pair_tlh",
        label="ETF-pair TLH baseline",
        rank=5,
        executable=False,
        summary="Swaps broad ETFs with highly correlated alternatives; simple but misses stock-level losses.",
        best_for="Baseline comparison only.",
        source_support=["Wealthfront ETF TLH support", "Israelov/Lu direct indexing vs ETF horserace"],
    ),
    DirectIndexModel(
        id="full_replication",
        label="Full replication direct indexing",
        rank=6,
        executable=False,
        summary="Owns every index constituent; maximizes tracking precision and lot count when account size supports it.",
        best_for="Large accounts with fractional shares and high operational capacity.",
        source_support=["Direct indexing provider literature", "Frec historical constituent simulations"],
    ),
    DirectIndexModel(
        id="tax_aware_reinvestment",
        label="Tax-aware reinvestment",
        rank=7,
        executable=False,
        summary="Models quarterly reinvestment of realized tax savings and investor-specific tax rates.",
        best_for="Investors with external capital gains and high marginal tax rates.",
        source_support=["Frec reinvestment simulations", "Sosner/Gromis/Krasner investor tax-profile work"],
    ),
    DirectIndexModel(
        id="long_short_direct_indexing",
        label="Long-short direct indexing",
        rank=8,
        executable=False,
        summary="Uses long-short extensions and leverage to generate larger tax assets with materially higher complexity.",
        best_for="Research-only high-net-worth simulation; not suitable as the default app model.",
        source_support=["AQR dynamic direct long-short investing"],
    ),
)


def direct_index_model_config(model_id: str | None = None) -> DirectIndexModel:
    normalized = (model_id or DEFAULT_DIRECT_INDEX_MODEL).lower().strip()
    return EXECUTABLE_MODELS.get(normalized, EXECUTABLE_MODELS[DEFAULT_DIRECT_INDEX_MODEL])


def all_direct_index_models() -> list[DirectIndexModel]:
    return sorted([*EXECUTABLE_MODELS.values(), *RESEARCH_ONLY_MODELS], key=lambda model: model.rank)
