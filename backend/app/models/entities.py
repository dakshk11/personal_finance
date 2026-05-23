from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    portfolios: Mapped[list["Portfolio"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    thirteen_f_watches: Mapped[list["ThirteenFWatch"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    advisor_profile: Mapped["Advisor | None"] = relationship(back_populates="user")
    retirement_analyzer_state: Mapped["RetirementAnalyzerState | None"] = relationship(back_populates="user", cascade="all, delete-orphan")
    ai_advisor_openai_key: Mapped["AIAdvisorOpenAIKey | None"] = relationship(back_populates="user", cascade="all, delete-orphan")
    ai_advisor_reports: Mapped[list["AIAdvisorReport"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    personal_cfo_projects: Mapped[list["PersonalCFOProject"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RetirementAnalyzerState(Base):
    __tablename__ = "retirement_analyzer_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship(back_populates="retirement_analyzer_state")


class AIAdvisorOpenAIKey(Base):
    __tablename__ = "ai_advisor_openai_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    key_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship(back_populates="ai_advisor_openai_key")


class AIAdvisorReport(Base):
    __tablename__ = "ai_advisor_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    module_id: Mapped[str] = mapped_column(String(80), index=True)
    module_title: Mapped[str] = mapped_column(String(160))
    model: Mapped[str] = mapped_column(String(80))
    input_snapshot_json: Mapped[str] = mapped_column(Text)
    prompt_text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str] = mapped_column(Text)
    usage_json: Mapped[str] = mapped_column(Text, default="{}")
    error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="ai_advisor_reports")


class PersonalCFOProject(Base):
    __tablename__ = "personal_cfo_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="Investment Folder")
    status: Mapped[str] = mapped_column(String(40), default="interview", index=True)
    current_phase: Mapped[int] = mapped_column(Integer, default=1)
    phase_progress_json: Mapped[str] = mapped_column(Text, default="{}")
    one_pager_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    refinement_used: Mapped[bool] = mapped_column(Boolean, default=False)
    last_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship(back_populates="personal_cfo_projects")
    messages: Mapped[list["PersonalCFOMessage"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="PersonalCFOMessage.id",
    )
    files: Mapped[list["PersonalCFOFile"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="PersonalCFOFile.path",
    )
    uploads: Mapped[list["PersonalCFOUpload"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="PersonalCFOUpload.id",
    )


class PersonalCFOMessage(Base):
    __tablename__ = "personal_cfo_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("personal_cfo_projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    phase: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["PersonalCFOProject"] = relationship(back_populates="messages")


class PersonalCFOFile(Base):
    __tablename__ = "personal_cfo_files"
    __table_args__ = (UniqueConstraint("project_id", "path", name="uq_personal_cfo_project_file_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("personal_cfo_projects.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(60), default="markdown")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped["PersonalCFOProject"] = relationship(back_populates="files")


class PersonalCFOUpload(Base):
    __tablename__ = "personal_cfo_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("personal_cfo_projects.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(240))
    file_type: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    parsed_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["PersonalCFOProject"] = relationship(back_populates="uploads")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    advisors: Mapped[list["Advisor"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    clients: Mapped[list["Client"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Advisor(Base):
    __tablename__ = "advisors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="advisor_profile")
    organization: Mapped["Organization"] = relationship(back_populates="advisors")
    clients: Mapped[list["Client"]] = relationship(back_populates="advisor", cascade="all, delete-orphan")
    proposals: Mapped[list["Proposal"]] = relationship(back_populates="advisor", cascade="all, delete-orphan")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    advisor_id: Mapped[int] = mapped_column(ForeignKey("advisors.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    household_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    organization: Mapped["Organization"] = relationship(back_populates="clients")
    advisor: Mapped["Advisor"] = relationship(back_populates="clients")
    accounts: Mapped[list["Account"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    constraints: Mapped[list["ClientConstraint"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    equivalent_groups: Mapped[list["EquivalentSecurityGroup"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    proposals: Mapped[list["Proposal"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    account_type: Mapped[str] = mapped_column(String(80), default="taxable")
    taxable: Mapped[bool] = mapped_column(Boolean, default=True)
    custodian: Mapped[str | None] = mapped_column(String(120), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    client: Mapped["Client"] = relationship(back_populates="accounts")
    holdings: Mapped[list["ImportedHolding"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    tax_lots: Mapped[list["ImportedTaxLot"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    transition_plans: Mapped[list["TransitionPlan"]] = relationship(back_populates="account")


class ImportedHolding(Base):
    __tablename__ = "imported_holdings"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_imported_holding_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    market_value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(255), default="advisor import")
    as_of_date: Mapped[date] = mapped_column(Date)

    account: Mapped["Account"] = relationship(back_populates="holdings")


class ImportedTaxLot(Base):
    __tablename__ = "imported_tax_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    acquisition_date: Mapped[date] = mapped_column(Date)
    shares: Mapped[float] = mapped_column(Float)
    cost_basis_per_share: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(255), default="advisor import")

    account: Mapped["Account"] = relationship(back_populates="tax_lots")


class ClientConstraint(Base):
    __tablename__ = "client_constraints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    target_index: Mapped[str] = mapped_column(String(16), default="XLG")
    annual_gains_budget: Mapped[float] = mapped_column(Float, default=0)
    max_tracking_error: Mapped[float] = mapped_column(Float, default=0.05)
    max_active_share: Mapped[float] = mapped_column(Float, default=0.20)
    estimated_tax_rate: Mapped[float] = mapped_column(Float, default=0.35)
    excluded_symbols_json: Mapped[str] = mapped_column(Text, default="[]")
    excluded_sectors_json: Mapped[str] = mapped_column(Text, default="[]")
    household_wash_sale_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outside_accounts_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    client: Mapped["Client"] = relationship(back_populates="constraints")


class EquivalentSecurityGroup(Base):
    __tablename__ = "equivalent_security_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    symbols_json: Mapped[str] = mapped_column(Text)

    client: Mapped["Client"] = relationship(back_populates="equivalent_groups")


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    advisor_id: Mapped[int] = mapped_column(ForeignKey("advisors.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped["Client"] = relationship(back_populates="proposals")
    advisor: Mapped["Advisor"] = relationship(back_populates="proposals")
    transition_plan: Mapped["TransitionPlan | None"] = relationship(back_populates="proposal", cascade="all, delete-orphan")
    audit_events: Mapped[list["RecommendationAuditEvent"]] = relationship(back_populates="proposal", cascade="all, delete-orphan")


class TransitionPlan(Base):
    __tablename__ = "transition_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), unique=True, index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    algorithm_version: Mapped[str] = mapped_column(String(40))
    target_index: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    objective: Mapped[str] = mapped_column(String(40), default="transition_gradually")
    input_snapshot_json: Mapped[str] = mapped_column(Text)
    recommendations_json: Mapped[str] = mapped_column(Text)
    warnings_json: Mapped[str] = mapped_column(Text)
    data_source_summary: Mapped[str] = mapped_column(Text)
    portfolio_value: Mapped[float] = mapped_column(Float)
    target_value: Mapped[float] = mapped_column(Float)
    realized_gains: Mapped[float] = mapped_column(Float, default=0)
    realized_losses: Mapped[float] = mapped_column(Float, default=0)
    net_realized_gain: Mapped[float] = mapped_column(Float, default=0)
    estimated_tax_impact: Mapped[float] = mapped_column(Float, default=0)
    tracking_drift: Mapped[float] = mapped_column(Float, default=0)
    active_share: Mapped[float] = mapped_column(Float, default=0)
    turnover: Mapped[float] = mapped_column(Float, default=0)
    skipped_trade_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    proposal: Mapped["Proposal"] = relationship(back_populates="transition_plan")
    account: Mapped["Account | None"] = relationship(back_populates="transition_plans")


class RecommendationAuditEvent(Base):
    __tablename__ = "recommendation_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), index=True)
    transition_plan_id: Mapped[int | None] = mapped_column(ForeignKey("transition_plans.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    proposal: Mapped["Proposal"] = relationship(back_populates="audit_events")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


class DataSyncLog(Base):
    __tablename__ = "data_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(80), index=True)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)


class ThirteenFWatch(Base):
    __tablename__ = "thirteen_f_watches"
    __table_args__ = (UniqueConstraint("user_id", "cik", name="uq_thirteen_f_watch_user_cik"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(160))
    manager_name: Mapped[str] = mapped_column(String(255))
    cik: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    latest_form: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latest_accession_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    latest_filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_report_period: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_primary_document_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    latest_info_table_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship(back_populates="thirteen_f_watches")
    filings: Mapped[list["ThirteenFFiling"]] = relationship(back_populates="watch", cascade="all, delete-orphan")


class ThirteenFFiling(Base):
    __tablename__ = "thirteen_f_filings"
    __table_args__ = (UniqueConstraint("watch_id", "accession_number", name="uq_thirteen_f_filing_watch_accession"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("thirteen_f_watches.id", ondelete="CASCADE"), index=True)
    manager_name: Mapped[str] = mapped_column(String(255))
    cik: Mapped[str] = mapped_column(String(10), index=True)
    form: Mapped[str] = mapped_column(String(20))
    accession_number: Mapped[str] = mapped_column(String(32), index=True)
    filing_date: Mapped[date] = mapped_column(Date, index=True)
    report_period: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    primary_document_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    info_table_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_info_table_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    holdings_count: Mapped[int] = mapped_column(Integer, default=0)
    priced_holdings_count: Mapped[int] = mapped_column(Integer, default=0)
    total_value: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    watch: Mapped["ThirteenFWatch"] = relationship(back_populates="filings")
    holdings: Mapped[list["ThirteenFHolding"]] = relationship(back_populates="filing", cascade="all, delete-orphan")


class ThirteenFHolding(Base):
    __tablename__ = "thirteen_f_holdings"
    __table_args__ = (
        UniqueConstraint("filing_id", "cusip", "issuer_name", "title_class", "put_call", name="uq_thirteen_f_holding_filing_row"),
        Index("ix_thirteen_f_holding_filing_symbol", "filing_id", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("thirteen_f_filings.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    cusip: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    issuer_name: Mapped[str] = mapped_column(String(255))
    title_class: Mapped[str | None] = mapped_column(String(120), nullable=True)
    value: Mapped[float] = mapped_column(Float, default=0)
    shares: Mapped[float] = mapped_column(Float, default=0)
    put_call: Mapped[str | None] = mapped_column(String(8), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=0)

    filing: Mapped["ThirteenFFiling"] = relationship(back_populates="holdings")


class HoldingSnapshot(Base):
    __tablename__ = "holding_snapshots"
    __table_args__ = (
        UniqueConstraint("index_symbol", "as_of_date", "symbol", name="uq_holding_snapshot_symbol_date"),
        Index("ix_holding_snapshot_index_date", "index_symbol", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    index_symbol: Mapped[str] = mapped_column(String(16), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    weight: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(String(512))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("symbol", "price_date", name="uq_price_symbol_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    price_date: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[float] = mapped_column(Float)
    adjusted_close: Mapped[float] = mapped_column(Float)
    dividend: Mapped[float] = mapped_column(Float, default=0)
    split_ratio: Mapped[float] = mapped_column(Float, default=1)
    source: Mapped[str] = mapped_column(String(255))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SecurityMetricSnapshot(Base):
    __tablename__ = "security_metric_snapshots"
    __table_args__ = (UniqueConstraint("symbol", "metric_date", name="uq_security_metric_symbol_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    metric_date: Mapped[date] = mapped_column(Date, index=True)
    forward_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_pe_5y_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_pe_10y_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(255))
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    index_symbol: Mapped[str] = mapped_column(String(16), index=True)
    starting_value: Mapped[float] = mapped_column(Float, default=100_000)
    cash: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="portfolios")
    exclusions: Mapped[list["PortfolioExclusion"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    tax_lots: Mapped[list["TaxLot"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    trades: Mapped[list["Trade"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class PortfolioExclusion(Base):
    __tablename__ = "portfolio_exclusions"
    __table_args__ = (UniqueConstraint("portfolio_id", "symbol", name="uq_portfolio_exclusion_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="exclusions")


class TaxLot(Base):
    __tablename__ = "tax_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    acquisition_date: Mapped[date] = mapped_column(Date)
    shares: Mapped[float] = mapped_column(Float)
    cost_basis_per_share: Mapped[float] = mapped_column(Float)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="tax_lots")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    action: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    notional: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(32), default="simulated")
    index_symbol: Mapped[str] = mapped_column(String(16))
    realized_gain_loss: Mapped[float] = mapped_column(Float, default=0)
    harvested_loss: Mapped[float] = mapped_column(Float, default=0)
    tracking_impact: Mapped[float] = mapped_column(Float, default=0)
    wash_sale_status: Mapped[str] = mapped_column(String(80), default="cleared")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="trades")


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    index_symbol: Mapped[str] = mapped_column(String(16), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    starting_value: Mapped[float] = mapped_column(Float)
    ending_value: Mapped[float] = mapped_column(Float)
    benchmark_value: Mapped[float] = mapped_column(Float)
    tracking_difference: Mapped[float] = mapped_column(Float)
    tracking_error: Mapped[float] = mapped_column(Float)
    harvested_losses: Mapped[float] = mapped_column(Float)
    trade_count: Mapped[int] = mapped_column(Integer)
    tlh_trade_count: Mapped[int] = mapped_column(Integer)
    dropped_tlh_candidates: Mapped[int] = mapped_column(Integer)
    coverage_label: Mapped[str] = mapped_column(String(80))
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
