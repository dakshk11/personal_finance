"use client";

import {
  AlertTriangle,
  BarChart3,
  Calculator,
  CircleHelp,
  Landmark,
  LineChart as LineChartIcon,
  PiggyBank,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  WalletCards
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { apiFetch, currency, percent } from "@/lib/api";

type AccountKey = "taxable" | "taxDeferred" | "roth" | "cash";
type ScenarioName = "default" | "taxAware";
type SpendingModel = "inflationAdjusted" | "retirementSmile";

type AccountInput = {
  balance: number;
  contribution: number;
  basisPct: number;
};

type AccountInputs = Record<AccountKey, AccountInput>;

type AnalyzerSavedState = Partial<Omit<ProjectionInputs, "accounts">> & {
  accounts?: Partial<Record<AccountKey, Partial<AccountInput>>>;
};

type AnalyzerStateResponse = {
  payload: AnalyzerSavedState;
  updated_at?: string | null;
};

type ProjectionInputs = {
  currentAge: number;
  retirementAge: number;
  lifeExpectancy: number;
  currentIncome: number;
  retirementSpending: number;
  essentialSpending: number;
  spendingModel: SpendingModel;
  currentState: string;
  currentStateTaxRate: number;
  retirementState: string;
  retirementStateTaxRate: number;
  stateCapitalGainsRate: number;
  stateSocialSecurityTaxablePct: number;
  statePensionTaxablePct: number;
  socialSecurityAge: number;
  socialSecurityAnnual: number;
  pensionAnnual: number;
  legacyGoal: number;
  inflationRate: number;
  preRetirementReturn: number;
  postRetirementReturn: number;
  retirementTaxRate: number;
  currentTaxRate: number;
  capitalGainsRate: number;
  rothConversionBudget: number;
  rothConversionStartAge: number;
  marketShock: number;
  cashBucketYears: number;
  bondBucketYears: number;
  accounts: AccountInputs;
};

type BalanceSet = Record<AccountKey, number>;

type ProjectionRow = {
  year: number;
  age: number;
  retired: boolean;
  beginningPortfolio: number;
  endingPortfolio: number;
  returnBase: number;
  investmentReturn: number;
  portfolioReturnRate: number;
  spending: number;
  grossStableIncome: number;
  stableIncome: number;
  withdrawalNeed: number;
  grossWithdrawals: number;
  taxes: number;
  federalTaxes: number;
  rothConversion: number;
  rmd: number;
  taxableWithdrawal: number;
  taxDeferredWithdrawal: number;
  rothWithdrawal: number;
  cashWithdrawal: number;
  taxableBalance: number;
  taxDeferredBalance: number;
  rothBalance: number;
  cashBalance: number;
  stateTaxes: number;
  effectiveTaxRate: number;
  shortfall: number;
};

type StrategyResult = {
  name: ScenarioName;
  rows: ProjectionRow[];
  totalTaxes: number;
  finalBalance: number;
  shortfallYears: number;
  depletedAge: number | null;
  confidence: number;
  startWithdrawalRate: number;
  guardrailLowRate: number;
  guardrailHighRate: number;
  lowerBalanceTrigger: number;
  upperBalanceTrigger: number;
  dynamicAnnualSpend: number;
  guardrailAction: "raise" | "hold" | "reduce";
  rothConversions: number;
  rmdTotal: number;
};

type SpendingSmileMilestone = {
  label: string;
  age: number;
  annual: number;
  monthly: number;
  realMultiplier: number;
  note: string;
};

type RothConversionAnalysis = {
  status: string;
  suggestedAnnualConversion: number;
  estimatedAnnualTaxFromBrokerage: number;
  totalWindowConversion: number;
  totalWindowTaxFromBrokerage: number;
  windowYears: number;
  lowBracketYears: number;
  brokerageCoverageYears: number | null;
  effectiveConversionTaxRate: number;
  currentBlendedTaxRate: number;
  preTaxShare: number;
  reason: string;
  partialReason: string;
  amountReason: string;
  taxFundingReason: string;
  windowReason: string;
  taxEfficiencyReason: string;
  limitingFactor: string;
  conversionStartAge: number;
  conversionEndAge: number;
  projectedTaxDeferredAtStart: number;
  projectedPortfolioAtStart: number;
  modeledAnnualConversion: number;
  capLimited: boolean;
  modeledAnnualCap: number;
  annualPortfolioCap: number;
  annualPreTaxCap: number;
  annualWindowCap: number;
  taxRateFactor: number;
  windowQualityFactor: number;
  taxEfficiencySpread: number;
  futurePreTaxRate: number;
  conversionTaxRate: number;
  rmdPressurePremium: number;
};

type RetirementReturnAnalysis = {
  weightedAverageReturn: number;
  firstRetirementReturn: number;
  normalReturnAssumption: number;
  firstRetirementInvestmentReturn: number;
  averageAnnualInvestmentReturn: number;
  negativeReturnYears: number;
  retirementYears: number;
  returnReason: string;
  assumptionReason: string;
  shockReason: string;
  calculationReason: string;
};

type VolatilityBucket = {
  label: string;
  location: string;
  target: number;
  current: number | null;
  status: string;
  guidance: string;
  examples: string[];
};

type VolatilityGuidance = {
  annualNetWithdrawalNeed: number;
  essentialNetNeed: number;
  bucketWithdrawalBase: number;
  cashYears: number;
  bondYears: number;
  crisisCoverageYears: number;
  buckets: VolatilityBucket[];
};

type PreRetirementIncomeAnalysis = {
  grossAnnualIncome: number;
  federalTaxRate: number;
  stateTaxRate: number;
  blendedTaxRate: number;
  federalTaxes: number;
  stateTaxes: number;
  annualTaxes: number;
  netAnnualIncome: number;
  netMonthlyIncome: number;
  yearsToRetirement: number;
  totalNetIncomeToRetirement: number;
  annualContributions: number;
  availableAfterContributions: number;
};

const accountMeta: Array<{ key: AccountKey; label: string; shortLabel: string; helper: string }> = [
  { key: "taxable", label: "Taxable brokerage", shortLabel: "Taxable", helper: "Brokerage, joint, trust, concentrated stock" },
  { key: "taxDeferred", label: "Tax-deferred", shortLabel: "Pre-tax", helper: "401(k), 403(b), traditional IRA" },
  { key: "roth", label: "Roth / HSA", shortLabel: "Roth", helper: "Roth IRA, Roth 401(k), HSA growth bucket" },
  { key: "cash", label: "Cash reserve", shortLabel: "Cash", helper: "Checking, savings, T-bills, money market" }
];

const stateOptions = [
  { value: "AL", label: "Alabama" },
  { value: "AK", label: "Alaska" },
  { value: "AZ", label: "Arizona" },
  { value: "AR", label: "Arkansas" },
  { value: "CA", label: "California" },
  { value: "CO", label: "Colorado" },
  { value: "CT", label: "Connecticut" },
  { value: "DE", label: "Delaware" },
  { value: "DC", label: "District of Columbia" },
  { value: "FL", label: "Florida" },
  { value: "GA", label: "Georgia" },
  { value: "HI", label: "Hawaii" },
  { value: "ID", label: "Idaho" },
  { value: "IL", label: "Illinois" },
  { value: "IN", label: "Indiana" },
  { value: "IA", label: "Iowa" },
  { value: "KS", label: "Kansas" },
  { value: "KY", label: "Kentucky" },
  { value: "LA", label: "Louisiana" },
  { value: "ME", label: "Maine" },
  { value: "MD", label: "Maryland" },
  { value: "MA", label: "Massachusetts" },
  { value: "MI", label: "Michigan" },
  { value: "MN", label: "Minnesota" },
  { value: "MS", label: "Mississippi" },
  { value: "MO", label: "Missouri" },
  { value: "MT", label: "Montana" },
  { value: "NE", label: "Nebraska" },
  { value: "NV", label: "Nevada" },
  { value: "NH", label: "New Hampshire" },
  { value: "NJ", label: "New Jersey" },
  { value: "NM", label: "New Mexico" },
  { value: "NY", label: "New York" },
  { value: "NC", label: "North Carolina" },
  { value: "ND", label: "North Dakota" },
  { value: "OH", label: "Ohio" },
  { value: "OK", label: "Oklahoma" },
  { value: "OR", label: "Oregon" },
  { value: "PA", label: "Pennsylvania" },
  { value: "RI", label: "Rhode Island" },
  { value: "SC", label: "South Carolina" },
  { value: "SD", label: "South Dakota" },
  { value: "TN", label: "Tennessee" },
  { value: "TX", label: "Texas" },
  { value: "UT", label: "Utah" },
  { value: "VT", label: "Vermont" },
  { value: "VA", label: "Virginia" },
  { value: "WA", label: "Washington" },
  { value: "WV", label: "West Virginia" },
  { value: "WI", label: "Wisconsin" },
  { value: "WY", label: "Wyoming" }
];

const defaultAccounts: AccountInputs = {
  taxable: { balance: 550000, contribution: 22000, basisPct: 70 },
  taxDeferred: { balance: 950000, contribution: 30000, basisPct: 0 },
  roth: { balance: 240000, contribution: 8000, basisPct: 100 },
  cash: { balance: 80000, contribution: 6000, basisPct: 100 }
};

const currentYear = 2026;
const MATERIAL_SHORTFALL_DOLLARS = 1;

export default function RetirementAnalyzerPage() {
  const [currentAge, setCurrentAge] = useState(52);
  const [retirementAge, setRetirementAge] = useState(65);
  const [lifeExpectancy, setLifeExpectancy] = useState(94);
  const [currentIncome, setCurrentIncome] = useState(240000);
  const [retirementSpending, setRetirementSpending] = useState(165000);
  const [essentialSpending, setEssentialSpending] = useState(98000);
  const [spendingModel, setSpendingModel] = useState<SpendingModel>("retirementSmile");
  const [currentState, setCurrentState] = useState("CA");
  const [currentStateTaxRate, setCurrentStateTaxRate] = useState(6);
  const [retirementState, setRetirementState] = useState("CA");
  const [retirementStateTaxRate, setRetirementStateTaxRate] = useState(6);
  const [stateCapitalGainsRate, setStateCapitalGainsRate] = useState(6);
  const [stateSocialSecurityTaxablePct, setStateSocialSecurityTaxablePct] = useState(0);
  const [statePensionTaxablePct, setStatePensionTaxablePct] = useState(100);
  const [saveStatus, setSaveStatus] = useState("Loading saved inputs");
  const [inputStateLoaded, setInputStateLoaded] = useState(false);
  const [autosaveEnabled, setAutosaveEnabled] = useState(false);
  const [socialSecurityAge, setSocialSecurityAge] = useState(70);
  const [socialSecurityAnnual, setSocialSecurityAnnual] = useState(52000);
  const [pensionAnnual, setPensionAnnual] = useState(18000);
  const [legacyGoal, setLegacyGoal] = useState(500000);
  const [inflationRate, setInflationRate] = useState(2.8);
  const [preRetirementReturn, setPreRetirementReturn] = useState(6.2);
  const [postRetirementReturn, setPostRetirementReturn] = useState(4.8);
  const [currentTaxRate, setCurrentTaxRate] = useState(32);
  const [retirementTaxRate, setRetirementTaxRate] = useState(24);
  const [capitalGainsRate, setCapitalGainsRate] = useState(18);
  const [rothConversionBudget, setRothConversionBudget] = useState(36000);
  const [rothConversionStartAge, setRothConversionStartAge] = useState(59.5);
  const [marketShock, setMarketShock] = useState(-16);
  const [cashBucketYears, setCashBucketYears] = useState(2);
  const [bondBucketYears, setBondBucketYears] = useState(5);
  const [accounts, setAccounts] = useState<AccountInputs>(defaultAccounts);

  const inputs = useMemo<ProjectionInputs>(() => ({
    currentAge,
    retirementAge,
    lifeExpectancy,
    currentIncome,
    retirementSpending,
    essentialSpending,
    spendingModel,
    currentState,
    currentStateTaxRate,
    retirementState,
    retirementStateTaxRate,
    stateCapitalGainsRate,
    stateSocialSecurityTaxablePct,
    statePensionTaxablePct,
    socialSecurityAge,
    socialSecurityAnnual,
    pensionAnnual,
    legacyGoal,
    inflationRate,
    preRetirementReturn,
    postRetirementReturn,
    retirementTaxRate,
    currentTaxRate,
    capitalGainsRate,
    rothConversionBudget,
    rothConversionStartAge,
    marketShock,
    cashBucketYears,
    bondBucketYears,
    accounts
  }), [
    accounts,
    bondBucketYears,
    capitalGainsRate,
    cashBucketYears,
    currentAge,
    currentIncome,
    currentTaxRate,
    currentState,
    currentStateTaxRate,
    essentialSpending,
    inflationRate,
    legacyGoal,
    lifeExpectancy,
    marketShock,
    pensionAnnual,
    postRetirementReturn,
    preRetirementReturn,
    retirementAge,
    retirementSpending,
    retirementState,
    retirementStateTaxRate,
    retirementTaxRate,
    rothConversionBudget,
    rothConversionStartAge,
    socialSecurityAge,
    socialSecurityAnnual,
    stateCapitalGainsRate,
    statePensionTaxablePct,
    stateSocialSecurityTaxablePct,
    spendingModel
  ]);

  const projection = useMemo(() => {
    const defaultResult = projectRetirement(inputs, "default");
    const taxAwareResult = projectRetirement(inputs, "taxAware");
    return { defaultResult, taxAwareResult };
  }, [inputs]);

  useEffect(() => {
    let active = true;
    async function loadSavedState() {
      try {
        const saved = await apiFetch<AnalyzerStateResponse>("/retirement-analyzer/state");
        if (!active) return;
        applySavedInputs(saved.payload ?? {});
        setAutosaveEnabled(true);
        setSaveStatus(saved.updated_at ? `Saved inputs loaded ${formatSavedAt(saved.updated_at)}` : "Inputs will autosave");
      } catch (err) {
        if (!active) return;
        const message = err instanceof Error ? err.message : "";
        setAutosaveEnabled(false);
        setSaveStatus(message.includes("Authentication") || message.includes("Session") ? "Log in to autosave inputs" : "Autosave unavailable");
      } finally {
        if (active) setInputStateLoaded(true);
      }
    }
    void loadSavedState();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!inputStateLoaded || !autosaveEnabled) return;
    const timeout = window.setTimeout(() => {
      setSaveStatus("Saving inputs");
      apiFetch<AnalyzerStateResponse>("/retirement-analyzer/state", {
        method: "PUT",
        body: JSON.stringify({ payload: inputs })
      })
        .then((saved) => setSaveStatus(saved.updated_at ? `Inputs saved ${formatSavedAt(saved.updated_at)}` : "Inputs saved"))
        .catch(() => setSaveStatus("Autosave failed"));
    }, 800);
    return () => window.clearTimeout(timeout);
  }, [autosaveEnabled, inputStateLoaded, inputs]);

  const { defaultResult, taxAwareResult } = projection;
  const firstRetirementYear = taxAwareResult.rows.find((row) => row.age >= retirementAge);
  const firstRetirementWindow = taxAwareResult.rows.filter((row) => row.age >= retirementAge).slice(0, 12);
  const preRetirementIncome = useMemo(() => buildPreRetirementIncomeAnalysis(inputs), [inputs]);
  const chartRows = taxAwareResult.rows
    .filter((row) => row.age === currentAge || row.age >= retirementAge || row.age % 2 === 0)
    .map((row) => ({
      age: row.age,
      portfolio: Math.round(row.endingPortfolio),
      spending: Math.round(row.spending),
      stableIncome: Math.round(row.retired ? row.stableIncome : preRetirementIncome.netAnnualIncome),
      withdrawals: Math.round(row.grossWithdrawals),
      taxes: Math.round(row.taxes)
    }));
  const accountChartRows = accountMeta.map((account) => ({
    name: account.shortLabel,
    value: accounts[account.key].balance
  }));
  const withdrawalFundingRows = firstRetirementWindow.map((row) => {
    const materialShortfall = row.shortfall > MATERIAL_SHORTFALL_DOLLARS ? row.shortfall : 0;
    return {
      age: row.age,
      stableIncome: Math.round(row.stableIncome),
      taxable: Math.round(row.taxableWithdrawal),
      taxDeferred: Math.round(row.taxDeferredWithdrawal),
      roth: Math.round(row.rothWithdrawal),
      cash: Math.round(row.cashWithdrawal),
      taxes: Math.round(row.taxes),
      shortfall: Math.round(materialShortfall),
      spending: Math.round(row.spending)
    };
  });
  const firstWindowShortfall = firstRetirementWindow.reduce(
    (total, row) => total + (row.shortfall > MATERIAL_SHORTFALL_DOLLARS ? row.shortfall : 0),
    0
  );
  const afterTaxDelta = taxAwareResult.finalBalance - defaultResult.finalBalance;
  const lifetimeStateTaxes = taxAwareResult.rows.reduce((total, row) => total + row.stateTaxes, 0);
  const totalContribution = preRetirementIncome.annualContributions;
  const currentSavingsRate = preRetirementIncome.netAnnualIncome > 0 ? totalContribution / preRetirementIncome.netAnnualIncome : 0;
  const currentStateLabel = stateLabel(currentState);
  const retirementStateLabel = stateLabel(retirementState);
  const spendingSmileMilestones = useMemo(() => buildSpendingSmileMilestones(inputs), [inputs]);
  const rothConversionAnalysis = useMemo(() => buildRothConversionAnalysis(inputs, taxAwareResult), [inputs, taxAwareResult]);
  const volatilityGuidance = useMemo(() => buildVolatilityGuidance(inputs, taxAwareResult), [inputs, taxAwareResult]);
  const retirementReturnAnalysis = useMemo(() => buildRetirementReturnAnalysis(inputs, taxAwareResult), [inputs, taxAwareResult]);
  const saveStatusClass = saveStatus.includes("failed") || saveStatus.includes("unavailable") ? "risk-pill" : autosaveEnabled ? "status-pill" : "reason-pill";

  function updateAccount(key: AccountKey, field: keyof AccountInput, value: number) {
    setAccounts((current) => ({
      ...current,
      [key]: {
        ...current[key],
        [field]: value
      }
    }));
  }

  function applySavedInputs(saved: AnalyzerSavedState) {
    setCurrentAge(numberFromSaved(saved.currentAge, currentAge));
    setRetirementAge(numberFromSaved(saved.retirementAge, retirementAge));
    setLifeExpectancy(numberFromSaved(saved.lifeExpectancy, lifeExpectancy));
    setCurrentIncome(numberFromSaved(saved.currentIncome, currentIncome));
    setRetirementSpending(numberFromSaved(saved.retirementSpending, retirementSpending));
    setEssentialSpending(numberFromSaved(saved.essentialSpending, essentialSpending));
    setSpendingModel(saved.spendingModel === "inflationAdjusted" ? "inflationAdjusted" : "retirementSmile");
    setCurrentState(stateFromSaved(saved.currentState, currentState));
    setCurrentStateTaxRate(numberFromSaved(saved.currentStateTaxRate, currentStateTaxRate));
    setRetirementState(stateFromSaved(saved.retirementState, retirementState));
    setRetirementStateTaxRate(numberFromSaved(saved.retirementStateTaxRate, retirementStateTaxRate));
    setStateCapitalGainsRate(numberFromSaved(saved.stateCapitalGainsRate, stateCapitalGainsRate));
    setStateSocialSecurityTaxablePct(numberFromSaved(saved.stateSocialSecurityTaxablePct, stateSocialSecurityTaxablePct));
    setStatePensionTaxablePct(numberFromSaved(saved.statePensionTaxablePct, statePensionTaxablePct));
    setSocialSecurityAge(numberFromSaved(saved.socialSecurityAge, socialSecurityAge));
    setSocialSecurityAnnual(numberFromSaved(saved.socialSecurityAnnual, socialSecurityAnnual));
    setPensionAnnual(numberFromSaved(saved.pensionAnnual, pensionAnnual));
    setLegacyGoal(numberFromSaved(saved.legacyGoal, legacyGoal));
    setInflationRate(numberFromSaved(saved.inflationRate, inflationRate));
    setPreRetirementReturn(numberFromSaved(saved.preRetirementReturn, preRetirementReturn));
    setPostRetirementReturn(numberFromSaved(saved.postRetirementReturn, postRetirementReturn));
    setCurrentTaxRate(numberFromSaved(saved.currentTaxRate, currentTaxRate));
    setRetirementTaxRate(numberFromSaved(saved.retirementTaxRate, retirementTaxRate));
    setCapitalGainsRate(numberFromSaved(saved.capitalGainsRate, capitalGainsRate));
    setRothConversionBudget(numberFromSaved(saved.rothConversionBudget, rothConversionBudget));
    setRothConversionStartAge(numberFromSaved(saved.rothConversionStartAge, rothConversionStartAge));
    setMarketShock(numberFromSaved(saved.marketShock, marketShock));
    setCashBucketYears(numberFromSaved(saved.cashBucketYears, cashBucketYears));
    setBondBucketYears(numberFromSaved(saved.bondBucketYears, bondBucketYears));
    if (saved.accounts) {
      setAccounts((current) => ({
        taxable: mergeSavedAccount(current.taxable, saved.accounts?.taxable),
        taxDeferred: mergeSavedAccount(current.taxDeferred, saved.accounts?.taxDeferred),
        roth: mergeSavedAccount(current.roth, saved.accounts?.roth),
        cash: mergeSavedAccount(current.cash, saved.accounts?.cash)
      }));
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <Link href="/" className="brand"><span className="brand-mark">D</span><span>DirectIndex</span></Link>
          <h1>Retirement analyzer</h1>
        </div>
        <div className="dashboard-actions">
          <span className={saveStatusClass}>{saveStatus}</span>
          <Link className="ghost-button" href="/research">Research</Link>
          <Link className="ghost-button" href="/ideas">Ideas</Link>
          <Link className="ghost-button" href="/advisor">Advisor</Link>
          <Link className="secondary-button" href="/dashboard">Portfolio dashboard</Link>
        </div>
      </header>

      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      <div className="retirement-layout">
        <aside className="retirement-sidebar">
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Household inputs</h2>
              <SlidersHorizontal size={18} />
            </div>
            <div className="retirement-input-grid">
              <NumberField id="current-age" label="Current age" value={currentAge} onChange={setCurrentAge} min={18} max={90} />
              <NumberField id="retirement-age" label="Retirement age" value={retirementAge} onChange={setRetirementAge} min={currentAge} max={85} />
              <NumberField id="life-expectancy" label="Plan through age" value={lifeExpectancy} onChange={setLifeExpectancy} min={retirementAge + 1} max={105} />
              <NumberField id="social-security-age" label="Social Security age" value={socialSecurityAge} onChange={setSocialSecurityAge} min={62} max={70} />
            </div>
            <div className="form-stack" style={{ marginTop: 14 }}>
              <NumberField
                id="current-income"
                label="Current income"
                value={currentIncome}
                onChange={setCurrentIncome}
                min={0}
                step={5000}
                prefix="$"
                tooltip="Gross annual household income. The retirement analyzer assumes this income stays flat until retirement, then subtracts current federal and current-state tax to estimate after-tax income before retirement."
              />
              <NumberField id="retirement-spending" label="Annual retirement spending" value={retirementSpending} onChange={setRetirementSpending} min={0} step={2500} prefix="$" />
              <NumberField
                id="essential-spending"
                label="Essential annual spending"
                value={essentialSpending}
                onChange={setEssentialSpending}
                min={0}
                step={2500}
                prefix="$"
                tooltip="Annual retirement spending that should be protected even in a weak market: housing, food, healthcare, insurance, taxes, utilities, and basic transportation. The spending smile can reduce discretionary spending, but this essential amount stays as the floor."
              />
              <div className="field">
                <label htmlFor="spending-model">Spending model</label>
                <select id="spending-model" value={spendingModel} onChange={(event) => setSpendingModel(event.target.value as SpendingModel)}>
                  <option value="retirementSmile">Natural retirement smile</option>
                  <option value="inflationAdjusted">Inflation-adjusted flat real spend</option>
                </select>
              </div>
              <NumberField id="ss-benefit" label="Annual Social Security" value={socialSecurityAnnual} onChange={setSocialSecurityAnnual} min={0} step={1000} prefix="$" />
              <NumberField id="pension" label="Annual pension / annuity" value={pensionAnnual} onChange={setPensionAnnual} min={0} step={1000} prefix="$" />
              <NumberField
                id="legacy-goal"
                label="Legacy reserve target"
                value={legacyGoal}
                onChange={setLegacyGoal}
                min={0}
                step={25000}
                prefix="$"
                tooltip="Amount you want left at the end of the plan for inheritance, late-life care cushion, estate taxes, charitable giving, or emergency reserve. Ending assets above this target improve confidence; below it reduces confidence."
              />
            </div>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Accounts</h2>
              <WalletCards size={18} />
            </div>
            <div className="account-editor">
              {accountMeta.map((account) => (
                <div className="account-input-row" key={account.key}>
                  <div>
                    <strong>{account.label}</strong>
                    <span>{account.helper}</span>
                  </div>
                  <NumberField
                    id={`${account.key}-balance`}
                    label="Balance"
                    value={accounts[account.key].balance}
                    onChange={(value) => updateAccount(account.key, "balance", value)}
                    min={0}
                    step={5000}
                    prefix="$"
                  />
                  <NumberField
                    id={`${account.key}-contribution`}
                    label="Annual add"
                    value={accounts[account.key].contribution}
                    onChange={(value) => updateAccount(account.key, "contribution", value)}
                    min={0}
                    step={1000}
                    prefix="$"
                  />
                  {account.key === "taxable" ? (
                    <NumberField
                      id={`${account.key}-basis`}
                      label="Basis %"
                      value={accounts[account.key].basisPct}
                      onChange={(value) => updateAccount(account.key, "basisPct", value)}
                      min={0}
                      max={100}
                      suffix="%"
                    />
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Tax and markets</h2>
              <Calculator size={18} />
            </div>
            <div className="retirement-input-grid">
              <NumberField id="inflation" label="Inflation" value={inflationRate} onChange={setInflationRate} min={0} max={10} step={0.1} suffix="%" />
              <NumberField id="pre-return" label="Pre-ret return" value={preRetirementReturn} onChange={setPreRetirementReturn} min={-10} max={15} step={0.1} suffix="%" />
              <NumberField
                id="post-return"
                label="Retirement return assumption"
                value={postRetirementReturn}
                onChange={setPostRetirementReturn}
                min={-10}
                max={15}
                step={0.1}
                suffix="%"
                tooltip="User-entered annual portfolio return assumption after retirement, before withdrawals and taxes. The weighted return output can be lower because it blends cash reserves, the first retirement-year shock, and portfolio size through time."
              />
              <NumberField id="shock" label="Retirement shock" value={marketShock} onChange={setMarketShock} min={-50} max={10} step={1} suffix="%" />
              <NumberField
                id="current-tax"
                label="Federal current tax"
                value={currentTaxRate}
                onChange={setCurrentTaxRate}
                min={0}
                max={50}
                step={1}
                suffix="%"
                tooltip="Federal ordinary income tax rate applied to current income before retirement. The calculator assumes current income stays flat and subtracts this tax plus current-state tax to estimate pre-retirement after-tax income."
              />
              <NumberField id="retirement-tax" label="Federal retirement tax" value={retirementTaxRate} onChange={setRetirementTaxRate} min={0} max={50} step={1} suffix="%" />
              <NumberField id="capital-gains-tax" label="Federal cap gains tax" value={capitalGainsRate} onChange={setCapitalGainsRate} min={0} max={35} step={1} suffix="%" />
              <NumberField id="roth-conversion" label="Roth conversion" value={rothConversionBudget} onChange={setRothConversionBudget} min={0} step={2500} prefix="$" />
              <NumberField
                id="roth-conversion-start-age"
                label="Roth conversion start age"
                value={rothConversionStartAge}
                onChange={setRothConversionStartAge}
                min={59.5}
                max={85}
                step={0.5}
                tooltip="Age when tax-aware Roth conversions may begin. Default is 59.5 as a conservative penalty-aware start age for tax-deferred assets; the model still requires the household to be retired before conversions are projected."
              />
              <NumberField
                id="cash-bucket-years"
                label="Cash / T-bill years"
                value={cashBucketYears}
                onChange={setCashBucketYears}
                min={0}
                max={5}
                step={0.5}
                suffix="yrs"
                tooltip="Years of retirement withdrawals to target in cash, high-yield savings, money market funds, or Treasury bills before selling longer-term assets."
              />
              <NumberField
                id="bond-bucket-years"
                label="Bond bucket years"
                value={bondBucketYears}
                onChange={setBondBucketYears}
                min={0}
                max={12}
                step={0.5}
                suffix="yrs"
                tooltip="Years of withdrawals to target in high-quality bonds, TIPS, CDs, or a Treasury/bond ladder after the cash bucket. This is the buffer intended to avoid selling stocks during long bear markets."
              />
            </div>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>State tax details</h2>
              <Landmark size={18} />
            </div>
            <div className="state-tax-grid">
              <div className="field">
                <label htmlFor="current-state">Current state</label>
                <select id="current-state" value={currentState} onChange={(event) => setCurrentState(event.target.value)}>
                  {stateOptions.map((state) => <option key={`current-${state.value}`} value={state.value}>{state.label}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="retirement-state">Retirement state</label>
                <select id="retirement-state" value={retirementState} onChange={(event) => setRetirementState(event.target.value)}>
                  {stateOptions.map((state) => <option key={`retirement-${state.value}`} value={state.value}>{state.label}</option>)}
                </select>
              </div>
              <NumberField
                id="current-state-income-tax"
                label="Current state ordinary tax"
                value={currentStateTaxRate}
                onChange={setCurrentStateTaxRate}
                min={0}
                max={20}
                step={0.1}
                suffix="%"
                tooltip="State ordinary income tax rate to subtract from current income before retirement. This is separate from retirement-state tax so a future move can be modeled."
              />
              <NumberField id="state-income-tax" label="Retirement state ordinary tax" value={retirementStateTaxRate} onChange={setRetirementStateTaxRate} min={0} max={20} step={0.1} suffix="%" />
              <NumberField id="state-cap-gains-tax" label="State cap gains tax" value={stateCapitalGainsRate} onChange={setStateCapitalGainsRate} min={0} max={20} step={0.1} suffix="%" />
              <NumberField id="state-ss-taxable" label="State taxable SS" value={stateSocialSecurityTaxablePct} onChange={setStateSocialSecurityTaxablePct} min={0} max={100} step={5} suffix="%" />
              <NumberField id="state-pension-taxable" label="State taxable pension" value={statePensionTaxablePct} onChange={setStatePensionTaxablePct} min={0} max={100} step={5} suffix="%" />
            </div>
            <p className="fine-print">
              State rates and taxable income shares are user-entered assumptions. Current state tax is used before retirement; retirement state tax is used for pension, Social Security, withdrawals, and Roth conversions after retirement.
            </p>
          </section>
        </aside>

        <section className="retirement-workspace">
          <div className="stat-grid retirement-stat-grid">
            <article className="stat-panel">
              <ShieldCheck size={20} />
              <h3>Confidence zone</h3>
              <strong>{Math.round(taxAwareResult.confidence)}%</strong>
              <p>{confidenceLabel(taxAwareResult.confidence)} plan based on deterministic stress testing.</p>
            </article>
            <article className="stat-panel">
              <RefreshCw size={20} />
              <h3>Dynamic paycheck</h3>
              <strong>{currency(taxAwareResult.dynamicAnnualSpend / 12)}</strong>
              <p>{guardrailCopy(taxAwareResult.guardrailAction)} at retirement start.</p>
            </article>
            <article className="stat-panel">
              <Landmark size={20} />
              <h3>Tax-aware delta</h3>
              <strong>{currency(afterTaxDelta)}</strong>
              <p>{currency(defaultResult.totalTaxes - taxAwareResult.totalTaxes)} estimated lifetime tax difference, including state assumptions.</p>
            </article>
            <article className="stat-panel">
              <PiggyBank size={20} />
              <h3>End reserve</h3>
              <strong>{currency(taxAwareResult.finalBalance)}</strong>
              <p>{taxAwareResult.depletedAge ? `Depletes at age ${taxAwareResult.depletedAge}.` : `${currency(Math.max(0, taxAwareResult.finalBalance - legacyGoal))} above target.`}</p>
            </article>
          </div>

          <section className="dashboard-panel retirement-plan-summary">
            <div className="panel-header">
              <h2>Goal confidence and cash-flow map</h2>
              <div className="inline-actions">
                <span className="reason-pill">After-tax savings rate {percent(currentSavingsRate)}</span>
                <span className="reason-pill">Net income {currency(preRetirementIncome.netMonthlyIncome)}/mo</span>
                <span className="reason-pill">{spendingModelLabel(spendingModel)}</span>
                <span className="reason-pill">{currentStateLabel} to {retirementStateLabel}</span>
                <span className="reason-pill">Horizon {Math.max(1, lifeExpectancy - currentAge)} years</span>
                <span className={taxAwareResult.shortfallYears ? "risk-pill" : "status-pill"}>
                  {taxAwareResult.shortfallYears ? `${taxAwareResult.shortfallYears} shortfall years` : "Fully funded"}
                </span>
              </div>
            </div>
            <div className="insight-list compact">
              <div>
                <span>Gross income held flat</span>
                <strong>{currency(preRetirementIncome.grossAnnualIncome)}</strong>
              </div>
              <div>
                <span>Current tax removed</span>
                <strong>{currency(preRetirementIncome.annualTaxes)}</strong>
              </div>
              <div>
                <span>After-tax income until retirement</span>
                <strong>{currency(preRetirementIncome.netAnnualIncome)}</strong>
              </div>
              <div>
                <span>After account additions</span>
                <strong>{currency(preRetirementIncome.availableAfterContributions)}</strong>
              </div>
            </div>
            <p className="outcome-note">
              Current income is modeled as flat for {formatYearCount(preRetirementIncome.yearsToRetirement)} years until retirement. The model subtracts {percent(preRetirementIncome.federalTaxRate)} federal current tax and {percent(preRetirementIncome.stateTaxRate)} current-state tax before comparing annual account additions.
            </p>
            <div className="retirement-summary-grid">
              <div className="income-gauge">
                <span>Retirement start</span>
                <strong>{firstRetirementYear ? currency(firstRetirementYear.beginningPortfolio) : currency(0)}</strong>
                <div className="gauge-track">
                  <i style={{ width: `${clamp(taxAwareResult.confidence, 5, 98)}%` }} />
                </div>
                <small>{currency(retirementSpending)} planned spending, {currency(essentialSpending)} essential floor</small>
              </div>
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={chartRows}>
                  <CartesianGrid stroke="#dfe7e3" vertical={false} />
                  <XAxis dataKey="age" />
                  <YAxis tickFormatter={compactCurrency} />
                  <Tooltip formatter={(value) => typeof value === "number" ? currency(value) : value} />
                  <Line type="monotone" dataKey="portfolio" stroke="#0f766e" strokeWidth={3} dot={false} name="Portfolio" />
                  <Line type="monotone" dataKey="spending" stroke="#d97706" strokeWidth={2} dot={false} name="Spending" />
                  <Line type="monotone" dataKey="stableIncome" stroke="#2563eb" strokeWidth={2} dot={false} name="Income" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="retirement-analysis-grid">
            <article className="dashboard-panel">
              <div className="panel-header">
                <h2>Dynamic withdrawal guardrails</h2>
                <LineChartIcon size={18} />
              </div>
              <div className="guardrail-grid">
                <div className="guardrail-card reduce">
                  <span>Reduce trigger</span>
                  <strong>{currency(taxAwareResult.lowerBalanceTrigger)}</strong>
                  <small>Portfolio below this level implies a {percent(taxAwareResult.guardrailHighRate)} withdrawal rate.</small>
                </div>
                <div className="guardrail-card hold">
                  <span>Current path</span>
                  <strong>{percent(taxAwareResult.startWithdrawalRate)}</strong>
                  <small>Initial portfolio withdrawal rate after stable income.</small>
                </div>
                <div className="guardrail-card raise">
                  <span>Raise trigger</span>
                  <strong>{currency(taxAwareResult.upperBalanceTrigger)}</strong>
                  <small>Portfolio above this level implies a {percent(taxAwareResult.guardrailLowRate)} withdrawal rate.</small>
                </div>
              </div>
              <p className="outcome-note">
                Suggested annual spending is {currency(taxAwareResult.dynamicAnnualSpend)} with guardrails refigured from spending needs, stable income, and the retirement-start balance.
              </p>
            </article>

            <article className="dashboard-panel">
              <div className="panel-header">
                <h2>Current account mix</h2>
                <BarChart3 size={18} />
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={accountChartRows}>
                  <CartesianGrid stroke="#dfe7e3" vertical={false} />
                  <XAxis dataKey="name" />
                  <YAxis tickFormatter={compactCurrency} />
                  <Tooltip formatter={(value) => typeof value === "number" ? currency(value) : value} />
                  <Bar dataKey="value" fill="#0f766e" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </article>
          </section>

          <section className="retirement-analysis-grid">
            <article className="dashboard-panel">
              <div className="panel-header">
                <h2>Natural spending smile</h2>
                <RefreshCw size={18} />
              </div>
              <div className="milestone-grid">
                {spendingSmileMilestones.map((milestone) => (
                  <div className="milestone-card" key={milestone.label}>
                    <span>{milestone.label}</span>
                    <strong>{currency(milestone.annual)}</strong>
                    <small>Age {milestone.age} / {currency(milestone.monthly)} monthly</small>
                    <p>{milestone.note} Real spend factor {percent(milestone.realMultiplier)}.</p>
                  </div>
                ))}
              </div>
              <p className="outcome-note">
                The model keeps essential spending as a floor, then lets discretionary spending dip in mid-retirement and partially rise again late in life.
              </p>
            </article>

            <article className="dashboard-panel">
              <div className="panel-header">
                <h2>Roth conversion readout</h2>
                <Calculator size={18} />
              </div>
              <div className="conversion-summary">
                <span className={rothConversionAnalysis.suggestedAnnualConversion > 0 ? "status-pill" : "risk-pill"}>{rothConversionAnalysis.status}</span>
                <strong>{currency(rothConversionAnalysis.suggestedAnnualConversion)}</strong>
                <small>Suggested annual conversion</small>
              </div>
              <div className="insight-list compact">
                <div>
                  <span>Tax from brokerage</span>
                  <strong>{currency(rothConversionAnalysis.estimatedAnnualTaxFromBrokerage)}</strong>
                </div>
                <div>
                  <span>Modeled with cap</span>
                  <strong>{currency(rothConversionAnalysis.modeledAnnualConversion)}</strong>
                </div>
                <div>
                  <span>Tax-deferred at start</span>
                  <strong>{currency(rothConversionAnalysis.projectedTaxDeferredAtStart)}</strong>
                </div>
                <div>
                  <span>Window total</span>
                  <strong>{currency(rothConversionAnalysis.totalWindowConversion)}</strong>
                </div>
                <div>
                  <span>Brokerage required</span>
                  <strong>{currency(rothConversionAnalysis.totalWindowTaxFromBrokerage)}</strong>
                </div>
                <div>
                  <span>Conversion tax rate</span>
                  <strong>{percent(rothConversionAnalysis.effectiveConversionTaxRate)}</strong>
                </div>
              </div>
              <div className="analysis-disclosure-list">
                <details className="analysis-disclosure">
                  <summary><span>Why consider partial?</span><strong>{rothConversionAnalysis.status}</strong></summary>
                  <p>{rothConversionAnalysis.partialReason}</p>
                </details>
                <details className="analysis-disclosure">
                  <summary><span>How amount was chosen</span><strong>{currency(rothConversionAnalysis.suggestedAnnualConversion)} / yr</strong></summary>
                  <p>{rothConversionAnalysis.amountReason}</p>
                  <div className="disclosure-metric-grid">
                    <span><b>Start age</b>{formatAge(rothConversionAnalysis.conversionStartAge)}</span>
                    <span><b>Projected pre-tax</b>{currency(rothConversionAnalysis.projectedTaxDeferredAtStart)}</span>
                    <span><b>User cap</b>{currency(rothConversionAnalysis.modeledAnnualCap)}</span>
                    <span><b>Portfolio guardrail</b>{currency(rothConversionAnalysis.annualPortfolioCap)}</span>
                    <span><b>Pre-tax guardrail</b>{currency(rothConversionAnalysis.annualPreTaxCap)}</span>
                    <span><b>Window guardrail</b>{currency(rothConversionAnalysis.annualWindowCap)}</span>
                    <span><b>Tax efficiency</b>{percent(rothConversionAnalysis.taxRateFactor)}</span>
                    <span><b>Window factor</b>{percent(rothConversionAnalysis.windowQualityFactor)}</span>
                  </div>
                </details>
                <details className="analysis-disclosure">
                  <summary><span>Brokerage tax funding</span><strong>{currency(rothConversionAnalysis.estimatedAnnualTaxFromBrokerage)} / yr</strong></summary>
                  <p>{rothConversionAnalysis.taxFundingReason}</p>
                </details>
                <details className="analysis-disclosure">
                  <summary><span>Tax efficiency</span><strong>{percent(rothConversionAnalysis.taxEfficiencySpread)} spread</strong></summary>
                  <p>{rothConversionAnalysis.taxEfficiencyReason}</p>
                </details>
                <details className="analysis-disclosure">
                  <summary><span>Tax window</span><strong>{formatYearCount(rothConversionAnalysis.windowYears)} years</strong></summary>
                  <p>{rothConversionAnalysis.windowReason}</p>
                </details>
              </div>
            </article>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Retirement-year return output</h2>
              <div className="inline-actions">
                <span className="reason-pill">Assumption {percent(retirementReturnAnalysis.normalReturnAssumption)}</span>
                <span className="reason-pill">Avg {percent(retirementReturnAnalysis.weightedAverageReturn)}</span>
                <span className="reason-pill">First year {percent(retirementReturnAnalysis.firstRetirementReturn)}</span>
              </div>
            </div>
            <div className="return-assumption-bar">
              <div className="return-assumption-control">
                <NumberField
                  id="retirement-return-assumption"
                  label="Retirement return assumption"
                  value={postRetirementReturn}
                  onChange={setPostRetirementReturn}
                  min={-10}
                  max={15}
                  step={0.1}
                  suffix="%"
                  tooltip="Change this if you want the retirement years to use a different return assumption. It feeds the projection, the weighted return output, guardrails, Roth conversion window, and year-by-year table."
                />
              </div>
              <details className="analysis-disclosure">
                <summary><span>Why not 7-8%?</span><strong>Blended retirement return</strong></summary>
                <p>{retirementReturnAnalysis.assumptionReason}</p>
              </details>
            </div>
            <div className="analysis-disclosure-grid">
              <details className="analysis-disclosure" open>
                <summary><span>Weighted retirement return</span><strong>{percent(retirementReturnAnalysis.weightedAverageReturn)}</strong></summary>
                <p>{retirementReturnAnalysis.returnReason}</p>
              </details>
              <details className="analysis-disclosure">
                <summary><span>First retirement year</span><strong>{percent(retirementReturnAnalysis.firstRetirementReturn)}</strong></summary>
                <p>{retirementReturnAnalysis.shockReason}</p>
              </details>
              <details className="analysis-disclosure">
                <summary><span>Annual investment return</span><strong>{currency(retirementReturnAnalysis.averageAnnualInvestmentReturn)}</strong></summary>
                <p>{retirementReturnAnalysis.calculationReason}</p>
              </details>
            </div>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Volatility reserve and account-location guide</h2>
              <div className="inline-actions">
                <span className="reason-pill">Withdrawal base {currency(volatilityGuidance.bucketWithdrawalBase)}</span>
                <span className="reason-pill">{formatYears(volatilityGuidance.crisisCoverageYears)} years before stocks</span>
              </div>
            </div>
            <div className="bucket-grid">
              {volatilityGuidance.buckets.map((bucket) => (
                <article className="bucket-card" key={bucket.label}>
                  <span>{bucket.label}</span>
                  <strong>{currency(bucket.target)}</strong>
                  <small>{bucket.location}</small>
                  {bucket.current !== null ? <em>{bucket.status}: {currency(bucket.current)}</em> : <em>{bucket.status}</em>}
                  <p>{bucket.guidance}</p>
                  <div className="bucket-examples">
                    <b>Examples</b>
                    <span>{bucket.examples.join(" / ")}</span>
                  </div>
                </article>
              ))}
            </div>
            <details className="analysis-disclosure research-note">
              <summary><span>Bucket research basis</span><strong>{formatYears(volatilityGuidance.cashYears)} cash + {formatYears(volatilityGuidance.bondYears)} bond years</strong></summary>
              <p>
                The target uses the net annual spending need not covered by pension or Social Security. Cash/T-bills fund the first {formatYears(volatilityGuidance.cashYears)} years, high-quality bonds fund the next {formatYears(volatilityGuidance.bondYears)} years, and stocks are the long-horizon bucket. The goal is to avoid forced stock sales during a multi-year bear market like the dot-com decline or Great Financial Crisis.
              </p>
            </details>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Tax-aware planning sequence</h2>
              <div className="inline-actions">
                <span className="reason-pill">{currency(taxAwareResult.rothConversions)} Roth conversions modeled</span>
                <span className="reason-pill">{currency(lifetimeStateTaxes)} state tax estimate</span>
              </div>
            </div>
            <div className="sequence-grid">
              <article className="sequence-step">
                <strong>1. Spend from taxable lots</strong>
                <span>Uses taxable basis first and recognizes capital gains only on the embedded gain portion.</span>
              </article>
              <article className="sequence-step">
                <strong>2. Fill low-bracket years</strong>
                <span>Converts tax-deferred assets after age {formatAge(Math.max(retirementAge, rothConversionStartAge))}, limited by the annual cap, tax efficiency, and pre-RMD window.</span>
              </article>
              <article className="sequence-step">
                <strong>3. Reserve Roth dollars</strong>
                <span>Roth assets are held for high-tax years, late-life spending shocks, and legacy reserve protection.</span>
              </article>
              <article className="sequence-step">
                <strong>4. Respect RMDs</strong>
                <span>{currency(taxAwareResult.rmdTotal)} of required distributions are modeled from age 73 onward.</span>
              </article>
            </div>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Annual spending funding mix</h2>
              <div className="inline-actions">
                <span className="reason-pill">Taxable vs tax-deferred</span>
                <span className={firstWindowShortfall > MATERIAL_SHORTFALL_DOLLARS ? "risk-pill" : "status-pill"}>
                  {firstWindowShortfall > MATERIAL_SHORTFALL_DOLLARS ? `${currency(firstWindowShortfall)} gap` : "No material gap"}
                </span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={285}>
              <ComposedChart data={withdrawalFundingRows}>
                <CartesianGrid stroke="#dfe7e3" vertical={false} />
                <XAxis dataKey="age" />
                <YAxis tickFormatter={compactCurrency} />
                <Tooltip formatter={(value) => typeof value === "number" ? currency(value) : value} />
                <Legend />
                <Bar dataKey="stableIncome" stackId="funding" name="Stable income" fill="#64748b" radius={[0, 0, 0, 0]} />
                <Bar dataKey="taxable" stackId="funding" name="Taxable" fill="#0f766e" radius={[0, 0, 0, 0]} />
                <Bar dataKey="taxDeferred" stackId="funding" name="Tax-deferred" fill="#7c3aed" radius={[0, 0, 0, 0]} />
                <Bar dataKey="roth" stackId="funding" name="Roth" fill="#2563eb" radius={[0, 0, 0, 0]} />
                <Bar dataKey="cash" stackId="funding" name="Cash" fill="#d97706" radius={[0, 0, 0, 0]} />
                <Bar dataKey="shortfall" stackId="funding" name="Unfunded gap" fill="#dc2626" radius={[4, 4, 0, 0]} />
                <Line type="monotone" dataKey="spending" name="Annual spending" stroke="#111827" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="outcome-note">
              The withdrawal bars are gross dollars to pull from each account for annual spending before taxes. Shortfall is only shown when the unfunded spending gap is greater than {currency(MATERIAL_SHORTFALL_DOLLARS)} after stable income and all modeled account withdrawals.
            </p>
          </section>

          <section className="dashboard-panel">
            <div className="table-header" style={{ marginBottom: 14 }}>
              <h2>Detailed retirement cash flow</h2>
              <div className="inline-actions">
                <span className="reason-pill">{firstRetirementWindow.length} annual rows</span>
                <span className="status-pill">Effective federal + state tax</span>
              </div>
            </div>
            <div className="table-wrap">
              <div className="retirement-year-table">
                <div className="retirement-year-row header">
                  <span>Year</span><span>Age</span><span>Beg. port.</span><span>Gross income</span><span>Spend</span><span>Net funded</span><span>Taxable</span><span>Pre-tax / RMD</span><span>Roth</span><span>Cash</span><span>Roth conv.</span><span>Fed tax</span><span>State tax</span><span>Eff. tax</span><span>Gap</span><span>End port.</span>
                </div>
                {firstRetirementWindow.map((row) => (
                  <div className="retirement-year-row" key={`${row.year}-${row.age}`}>
                    <span>{row.year}</span>
                    <span>{row.age}</span>
                    <strong>{currency(row.beginningPortfolio)}</strong>
                    <span>{currency(row.grossStableIncome)}</span>
                    <span>{currency(row.spending)}</span>
                    <span>{currency(Math.max(0, row.spending - (row.shortfall > MATERIAL_SHORTFALL_DOLLARS ? row.shortfall : 0)))}</span>
                    <span>{currency(row.taxableWithdrawal)}</span>
                    <span>{currency(row.taxDeferredWithdrawal)}</span>
                    <span>{currency(row.rothWithdrawal)}</span>
                    <span>{currency(row.cashWithdrawal)}</span>
                    <span>{currency(row.rothConversion)}</span>
                    <span>{currency(row.federalTaxes)}</span>
                    <span>{currency(row.stateTaxes)}</span>
                    <span>{percent(row.effectiveTaxRate)}</span>
                    <span>{currency(row.shortfall > MATERIAL_SHORTFALL_DOLLARS ? row.shortfall : 0)}</span>
                    <strong>{currency(row.endingPortfolio)}</strong>
                  </div>
                ))}
              </div>
            </div>
            <p className="outcome-note">
              Effective tax rate is total federal plus state tax divided by gross retirement cash flow for the year: pension/Social Security before tax, account withdrawals, RMDs, and any Roth conversion. The tax-aware scenario pulls from taxable, cash, pre-tax, and Roth accounts in the modeled order that keeps Roth dollars reserved and uses RMDs when required.
            </p>
          </section>

          <section className="feature-map-grid">
            <article className="dashboard-panel feature-map-card">
              <ShieldCheck size={20} />
              <h2>MoneyGuidePro-style confidence</h2>
              <p>Needs, wants, retirement age, savings rate, stress shock, and legacy reserve roll into one confidence zone.</p>
            </article>
            <article className="dashboard-panel feature-map-card">
              <Landmark size={20} />
              <h2>RightCapital-style tax planning</h2>
              <p>Taxable, pre-tax, Roth, cash, RMD, capital-gain, and Roth-conversion assumptions are shown as a sequenced plan.</p>
            </article>
            <article className="dashboard-panel feature-map-card">
              <RefreshCw size={20} />
              <h2>Income Lab-style guardrails</h2>
              <p>Spending raises and reductions are framed in dollar terms when the account balance crosses risk-based bands.</p>
            </article>
          </section>

          <section className="dashboard-panel retirement-warning">
            <AlertTriangle size={18} />
            <p>
              This is a deterministic planning simulation inspired by common advisor planning workflows. DirectIndex is not affiliated with MoneyGuidePro, RightCapital, or Income Lab, and this is not tax, legal, accounting, investment, fiduciary, brokerage, or trading advice.
            </p>
          </section>
        </section>
      </div>
    </main>
  );
}

function NumberField({
  id,
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  prefix,
  suffix,
  tooltip
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  prefix?: string;
  suffix?: string;
  tooltip?: string;
}) {
  return (
    <div className="field number-field">
      <div className="number-field-label-row">
        <label htmlFor={id}>{label}</label>
        {tooltip ? (
          <button className="tooltip-anchor" type="button" aria-label={tooltip}>
            <CircleHelp size={14} aria-hidden="true" />
            <span className="field-tooltip" role="tooltip">{tooltip}</span>
          </button>
        ) : null}
      </div>
      <div className="number-input-shell">
        {prefix ? <b>{prefix}</b> : null}
        <input
          id={id}
          type="number"
          min={min}
          max={max}
          step={step}
          value={Number.isFinite(value) ? value : 0}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {suffix ? <b>{suffix}</b> : null}
      </div>
    </div>
  );
}

function numberFromSaved(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function stateFromSaved(value: unknown, fallback: string) {
  return typeof value === "string" && stateOptions.some((state) => state.value === value) ? value : fallback;
}

function mergeSavedAccount(current: AccountInput, saved?: Partial<AccountInput>): AccountInput {
  return {
    balance: numberFromSaved(saved?.balance, current.balance),
    contribution: numberFromSaved(saved?.contribution, current.contribution),
    basisPct: numberFromSaved(saved?.basisPct, current.basisPct)
  };
}

function formatSavedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function projectRetirement(inputs: ProjectionInputs, name: ScenarioName): StrategyResult {
  const safeInputs = normalizeInputs(inputs);
  const balances: BalanceSet = {
    taxable: safeInputs.accounts.taxable.balance,
    taxDeferred: safeInputs.accounts.taxDeferred.balance,
    roth: safeInputs.accounts.roth.balance,
    cash: safeInputs.accounts.cash.balance
  };
  const rows: ProjectionRow[] = [];
  let totalTaxes = 0;
  let rothConversions = 0;
  let rmdTotal = 0;
  let shortfallYears = 0;
  let depletedAge: number | null = null;

  for (let age = safeInputs.currentAge; age <= safeInputs.lifeExpectancy; age += 1) {
    const retired = age >= safeInputs.retirementAge;
    const year = currentYear + age - safeInputs.currentAge;
    const beginningPortfolio = totalBalance(balances);
    const returnRate = (retired ? safeInputs.postRetirementReturn : safeInputs.preRetirementReturn) / 100;
    const appliedReturn = retired && age === safeInputs.retirementAge ? returnRate + safeInputs.marketShock / 100 : returnRate;
    const retirementYear = Math.max(0, age - safeInputs.retirementAge);

    if (!retired) {
      balances.taxable += safeInputs.accounts.taxable.contribution;
      balances.taxDeferred += safeInputs.accounts.taxDeferred.contribution;
      balances.roth += safeInputs.accounts.roth.contribution;
      balances.cash += safeInputs.accounts.cash.contribution;
    }

    const returnBase = totalBalance(balances);
    const cashReturnRate = Math.min(0.03, Math.max(0.01, appliedReturn / 3));
    balances.taxable = Math.max(0, balances.taxable * (1 + appliedReturn));
    balances.taxDeferred = Math.max(0, balances.taxDeferred * (1 + appliedReturn));
    balances.roth = Math.max(0, balances.roth * (1 + appliedReturn));
    balances.cash = Math.max(0, balances.cash * (1 + cashReturnRate));
    const afterReturnPortfolio = totalBalance(balances);
    const investmentReturn = afterReturnPortfolio - returnBase;
    const portfolioReturnRate = returnBase > 0 ? investmentReturn / returnBase : 0;

    let spending = 0;
    let grossStableIncome = 0;
    let stableIncome = 0;
    let withdrawalNeed = 0;
    let grossWithdrawals = 0;
    let taxes = 0;
    let federalTaxes = 0;
    let rothConversion = 0;
    let rmd = 0;
    let taxableWithdrawal = 0;
    let taxDeferredWithdrawal = 0;
    let rothWithdrawal = 0;
    let cashWithdrawal = 0;
    let stateTaxes = 0;
    let shortfall = 0;

    if (retired) {
      const inflationMultiplier = Math.pow(1 + safeInputs.inflationRate / 100, retirementYear);
      const socialSecurityMultiplier = Math.pow(1 + safeInputs.inflationRate / 100, Math.max(0, age - safeInputs.socialSecurityAge));
      spending = retirementSpendingForYear(safeInputs, retirementYear);
      const pensionIncome = safeInputs.pensionAnnual * inflationMultiplier;
      let socialSecurityIncome = 0;
      grossStableIncome = pensionIncome;
      if (age >= safeInputs.socialSecurityAge) {
        socialSecurityIncome = safeInputs.socialSecurityAnnual * socialSecurityMultiplier;
        grossStableIncome += socialSecurityIncome;
      }
      const federalOrdinaryRate = ordinaryTaxRate(safeInputs, name, age);
      const stateOrdinaryRate = stateOrdinaryTaxRate(safeInputs);
      const stableIncomeFederalTax = federalTaxOnStableIncome(safeInputs, pensionIncome, socialSecurityIncome, federalOrdinaryRate);
      const stableIncomeStateTax = stateTaxOnStableIncome(safeInputs, pensionIncome, socialSecurityIncome, stateOrdinaryRate);
      stableIncome = Math.max(0, grossStableIncome - stableIncomeFederalTax - stableIncomeStateTax);
      taxes += stableIncomeFederalTax + stableIncomeStateTax;
      federalTaxes += stableIncomeFederalTax;
      stateTaxes += stableIncomeStateTax;
      withdrawalNeed = Math.max(0, spending - stableIncome);

      let remainingNeed = withdrawalNeed;
      const ordinaryRate = clamp(federalOrdinaryRate + stateOrdinaryRate, 0, 0.95);
      const taxableStateRate = taxableWithdrawalStateTaxRate(safeInputs);
      const taxableRate = clamp(taxableWithdrawalTaxRate(safeInputs) + taxableStateRate, 0, 0.95);

      if (age >= 73 && balances.taxDeferred > 0) {
        rmd = Math.min(balances.taxDeferred, balances.taxDeferred / rmdDivisor(age));
        balances.taxDeferred -= rmd;
        const rmdTax = rmd * ordinaryRate;
        const rmdStateTax = rmd * stateOrdinaryRate;
        const rmdFederalTax = Math.max(0, rmdTax - rmdStateTax);
        const rmdAfterTax = Math.max(0, rmd - rmdTax);
        taxes += rmdTax;
        federalTaxes += rmdFederalTax;
        stateTaxes += rmdStateTax;
        grossWithdrawals += rmd;
        taxDeferredWithdrawal += rmd;
        rmdTotal += rmd;
        if (rmdAfterTax >= remainingNeed) {
          balances.taxable += rmdAfterTax - remainingNeed;
          remainingNeed = 0;
        } else {
          remainingNeed -= rmdAfterTax;
        }
      }

      const withdrawalResult = withdrawForSpending(
        balances,
        remainingNeed,
        withdrawalOrder(name, age, safeInputs),
        ordinaryRate,
        stateOrdinaryRate,
        taxableRate,
        taxableStateRate
      );
      balances.taxable = withdrawalResult.balances.taxable;
      balances.taxDeferred = withdrawalResult.balances.taxDeferred;
      balances.roth = withdrawalResult.balances.roth;
      balances.cash = withdrawalResult.balances.cash;
      grossWithdrawals += withdrawalResult.gross;
      taxes += withdrawalResult.taxes;
      federalTaxes += withdrawalResult.federalTaxes;
      stateTaxes += withdrawalResult.stateTaxes;
      taxableWithdrawal += withdrawalResult.byAccount.taxable;
      taxDeferredWithdrawal += withdrawalResult.byAccount.taxDeferred;
      rothWithdrawal += withdrawalResult.byAccount.roth;
      cashWithdrawal += withdrawalResult.byAccount.cash;
      shortfall = withdrawalResult.shortfall;

      const conversionStartAge = rothConversionEffectiveStartAge(safeInputs);
      const conversionEndAge = rothConversionEndAge();
      if (name === "taxAware" && age >= conversionStartAge && age < conversionEndAge && safeInputs.rothConversionBudget > 0 && balances.taxDeferred > 0) {
        const conversionDecision = rothConversionDecision(safeInputs, age, balances.taxDeferred, beginningPortfolio);
        rothConversion = Math.min(balances.taxDeferred, conversionDecision.amount * inflationMultiplier);
        const conversionTax = rothConversion * ordinaryRate;
        const conversionStateTax = rothConversion * stateOrdinaryRate;
        const conversionFederalTax = Math.max(0, conversionTax - conversionStateTax);
        balances.taxDeferred -= rothConversion;
        balances.roth += Math.max(0, rothConversion - conversionTax);
        rothConversions += rothConversion;
        taxes += conversionTax;
        federalTaxes += conversionFederalTax;
        stateTaxes += conversionStateTax;
      }

      if (shortfall > 1) {
        shortfallYears += 1;
        depletedAge = depletedAge ?? age;
      }
    }

    totalTaxes += taxes;
    const grossCashFlowForTaxRate = grossStableIncome + grossWithdrawals + rothConversion;
    rows.push({
      year,
      age,
      retired,
      beginningPortfolio,
      endingPortfolio: totalBalance(balances),
      returnBase,
      investmentReturn,
      portfolioReturnRate,
      spending,
      grossStableIncome,
      stableIncome,
      withdrawalNeed,
      grossWithdrawals,
      taxes,
      federalTaxes,
      rothConversion,
      rmd,
      taxableWithdrawal,
      taxDeferredWithdrawal,
      rothWithdrawal,
      cashWithdrawal,
      taxableBalance: balances.taxable,
      taxDeferredBalance: balances.taxDeferred,
      rothBalance: balances.roth,
      cashBalance: balances.cash,
      stateTaxes,
      effectiveTaxRate: grossCashFlowForTaxRate > 0 ? taxes / grossCashFlowForTaxRate : 0,
      shortfall
    });
  }

  const firstRetirementRow = rows.find((row) => row.age >= safeInputs.retirementAge);
  const firstWithdrawalNeed = firstRetirementRow?.withdrawalNeed ?? 0;
  const retirementPortfolio = Math.max(1, firstRetirementRow?.beginningPortfolio ?? totalBalance(balances));
  const startWithdrawalRate = clamp(firstWithdrawalNeed / retirementPortfolio, 0.015, 0.08);
  const guardrailLowRate = Math.max(0.01, startWithdrawalRate * 0.8);
  const guardrailHighRate = Math.max(guardrailLowRate + 0.005, startWithdrawalRate * 1.2);
  const lowerBalanceTrigger = firstWithdrawalNeed > 0 ? firstWithdrawalNeed / guardrailHighRate : retirementPortfolio;
  const upperBalanceTrigger = firstWithdrawalNeed > 0 ? firstWithdrawalNeed / guardrailLowRate : retirementPortfolio;
  const currentWithdrawalRate = firstRetirementRow && firstRetirementRow.beginningPortfolio > 0 ? firstWithdrawalNeed / firstRetirementRow.beginningPortfolio : startWithdrawalRate;
  const guardrailAction = currentWithdrawalRate > guardrailHighRate ? "reduce" : currentWithdrawalRate < guardrailLowRate ? "raise" : "hold";
  const dynamicAnnualSpend = guardrailAction === "reduce"
    ? safeInputs.retirementSpending * 0.9
    : guardrailAction === "raise"
      ? safeInputs.retirementSpending * 1.1
      : safeInputs.retirementSpending;
  const finalBalance = rows[rows.length - 1]?.endingPortfolio ?? 0;
  const confidence = calculateConfidence(finalBalance, safeInputs, startWithdrawalRate, shortfallYears, depletedAge);

  return {
    name,
    rows,
    totalTaxes,
    finalBalance,
    shortfallYears,
    depletedAge,
    confidence,
    startWithdrawalRate,
    guardrailLowRate,
    guardrailHighRate,
    lowerBalanceTrigger,
    upperBalanceTrigger,
    dynamicAnnualSpend,
    guardrailAction,
    rothConversions,
    rmdTotal
  };
}

function normalizeInputs(inputs: ProjectionInputs): ProjectionInputs {
  const currentAge = clamp(Math.round(inputs.currentAge), 18, 90);
  const retirementAge = clamp(Math.round(inputs.retirementAge), currentAge, 90);
  const lifeExpectancy = clamp(Math.round(inputs.lifeExpectancy), retirementAge + 1, 110);
  return {
    ...inputs,
    currentAge,
    retirementAge,
    lifeExpectancy,
    currentState: stateOptions.some((state) => state.value === inputs.currentState) ? inputs.currentState : "CA",
    currentStateTaxRate: clamp(inputs.currentStateTaxRate, 0, 20),
    retirementState: stateOptions.some((state) => state.value === inputs.retirementState) ? inputs.retirementState : "CA",
    socialSecurityAge: clamp(Math.round(inputs.socialSecurityAge), 62, 70),
    currentIncome: Math.max(0, inputs.currentIncome),
    retirementSpending: Math.max(0, inputs.retirementSpending),
    essentialSpending: Math.max(0, Math.min(inputs.essentialSpending, inputs.retirementSpending)),
    spendingModel: inputs.spendingModel === "inflationAdjusted" ? "inflationAdjusted" : "retirementSmile",
    socialSecurityAnnual: Math.max(0, inputs.socialSecurityAnnual),
    pensionAnnual: Math.max(0, inputs.pensionAnnual),
    legacyGoal: Math.max(0, inputs.legacyGoal),
    inflationRate: clamp(inputs.inflationRate, 0, 10),
    preRetirementReturn: clamp(inputs.preRetirementReturn, -20, 20),
    postRetirementReturn: clamp(inputs.postRetirementReturn, -20, 20),
    currentTaxRate: clamp(inputs.currentTaxRate, 0, 50),
    retirementTaxRate: clamp(inputs.retirementTaxRate, 0, 50),
    capitalGainsRate: clamp(inputs.capitalGainsRate, 0, 35),
    retirementStateTaxRate: clamp(inputs.retirementStateTaxRate, 0, 20),
    stateCapitalGainsRate: clamp(inputs.stateCapitalGainsRate, 0, 20),
    stateSocialSecurityTaxablePct: clamp(inputs.stateSocialSecurityTaxablePct, 0, 100),
    statePensionTaxablePct: clamp(inputs.statePensionTaxablePct, 0, 100),
    rothConversionBudget: Math.max(0, inputs.rothConversionBudget),
    rothConversionStartAge: clamp(inputs.rothConversionStartAge, 59.5, 85),
    marketShock: clamp(inputs.marketShock, -60, 20),
    cashBucketYears: clamp(inputs.cashBucketYears, 0, 5),
    bondBucketYears: clamp(inputs.bondBucketYears, 0, 12),
    accounts: {
      taxable: normalizeAccount(inputs.accounts.taxable),
      taxDeferred: normalizeAccount(inputs.accounts.taxDeferred),
      roth: normalizeAccount(inputs.accounts.roth),
      cash: normalizeAccount(inputs.accounts.cash)
    }
  };
}

function normalizeAccount(account: AccountInput): AccountInput {
  return {
    balance: Math.max(0, account.balance),
    contribution: Math.max(0, account.contribution),
    basisPct: clamp(account.basisPct, 0, 100)
  };
}

function retirementSpendingForYear(inputs: ProjectionInputs, retirementYear: number) {
  const inflationMultiplier = Math.pow(1 + inputs.inflationRate / 100, retirementYear);
  const realSpending = inputs.retirementSpending * retirementSmileMultiplier(inputs, retirementYear);
  const essentialFloor = inputs.essentialSpending * inflationMultiplier;
  return Math.max(essentialFloor, realSpending * inflationMultiplier);
}

function retirementSmileMultiplier(inputs: ProjectionInputs, retirementYear: number) {
  if (inputs.spendingModel === "inflationAdjusted") return 1;
  const retirementHorizon = Math.max(1, inputs.lifeExpectancy - inputs.retirementAge);
  const progress = clamp(retirementYear / retirementHorizon, 0, 1);
  const declinePhase = Math.min(progress, 0.62) / 0.62;
  const latePhase = progress > 0.62 ? (progress - 0.62) / 0.38 : 0;
  const midRetirementDecline = 0.16 * declinePhase;
  const lateLifeRise = 0.1 * latePhase;
  return clamp(1 - midRetirementDecline + lateLifeRise, 0.84, 1.02);
}

function withdrawForSpending(
  balances: BalanceSet,
  need: number,
  order: AccountKey[],
  ordinaryRate: number,
  ordinaryStateRate: number,
  taxableRate: number,
  taxableStateRate: number
) {
  const nextBalances: BalanceSet = { ...balances };
  const byAccount: BalanceSet = { taxable: 0, taxDeferred: 0, roth: 0, cash: 0 };
  let remainingNeed = Math.max(0, need);
  let gross = 0;
  let taxes = 0;
  let federalTaxes = 0;
  let stateTaxes = 0;

  for (const account of order) {
    if (remainingNeed <= 1 || nextBalances[account] <= 0) continue;
    const taxRate = account === "taxDeferred" ? ordinaryRate : account === "taxable" ? taxableRate : 0;
    const stateTaxRate = account === "taxDeferred" ? ordinaryStateRate : account === "taxable" ? taxableStateRate : 0;
    const grossNeeded = taxRate >= 0.95 ? remainingNeed : remainingNeed / (1 - taxRate);
    const withdrawal = Math.min(nextBalances[account], grossNeeded);
    const tax = withdrawal * taxRate;
    const stateTax = withdrawal * stateTaxRate;
    const federalTax = Math.max(0, tax - stateTax);
    const afterTax = Math.max(0, withdrawal - tax);
    nextBalances[account] -= withdrawal;
    byAccount[account] += withdrawal;
    gross += withdrawal;
    taxes += tax;
    federalTaxes += federalTax;
    stateTaxes += stateTax;
    remainingNeed -= afterTax;
  }

  return {
    balances: nextBalances,
    byAccount,
    gross,
    taxes,
    federalTaxes,
    stateTaxes,
    shortfall: Math.max(0, remainingNeed)
  };
}

function withdrawalOrder(name: ScenarioName, age: number, inputs: ProjectionInputs): AccountKey[] {
  if (name === "default") return ["taxable", "taxDeferred", "roth", "cash"];
  if (age < Math.min(73, inputs.socialSecurityAge)) return ["taxable", "cash", "taxDeferred", "roth"];
  return ["taxable", "taxDeferred", "cash", "roth"];
}

function ordinaryTaxRate(inputs: ProjectionInputs, name: ScenarioName, age: number) {
  const currentRate = inputs.currentTaxRate / 100;
  const retirementRate = inputs.retirementTaxRate / 100;
  if (name === "taxAware" && age < Math.min(73, inputs.socialSecurityAge)) {
    return Math.max(0, Math.min(retirementRate, currentRate - 0.04));
  }
  return retirementRate;
}

function taxableWithdrawalTaxRate(inputs: ProjectionInputs) {
  const gainPortion = Math.max(0, 1 - inputs.accounts.taxable.basisPct / 100);
  return gainPortion * (inputs.capitalGainsRate / 100);
}

function taxableWithdrawalStateTaxRate(inputs: ProjectionInputs) {
  const gainPortion = Math.max(0, 1 - inputs.accounts.taxable.basisPct / 100);
  return gainPortion * (inputs.stateCapitalGainsRate / 100);
}

function stateOrdinaryTaxRate(inputs: ProjectionInputs) {
  return inputs.retirementStateTaxRate / 100;
}

function currentStateOrdinaryTaxRate(inputs: ProjectionInputs) {
  return inputs.currentStateTaxRate / 100;
}

function stateTaxOnStableIncome(inputs: ProjectionInputs, pensionIncome: number, socialSecurityIncome: number, stateOrdinaryRate: number) {
  const taxablePension = pensionIncome * (inputs.statePensionTaxablePct / 100);
  const taxableSocialSecurity = socialSecurityIncome * (inputs.stateSocialSecurityTaxablePct / 100);
  return (taxablePension + taxableSocialSecurity) * stateOrdinaryRate;
}

function federalTaxOnStableIncome(_: ProjectionInputs, pensionIncome: number, socialSecurityIncome: number, federalOrdinaryRate: number) {
  const taxableSocialSecurity = socialSecurityIncome * 0.85;
  return (pensionIncome + taxableSocialSecurity) * federalOrdinaryRate;
}

function rmdDivisor(age: number) {
  return Math.max(3, 27.4 - Math.max(0, age - 73) * 0.9);
}

function calculateConfidence(
  finalBalance: number,
  inputs: ProjectionInputs,
  startWithdrawalRate: number,
  shortfallYears: number,
  depletedAge: number | null
) {
  if (depletedAge) {
    return clamp(22 - shortfallYears * 2 + Math.max(0, depletedAge - inputs.retirementAge), 5, 45);
  }
  const legacyGap = finalBalance - inputs.legacyGoal;
  const spendingAnchor = Math.max(1, inputs.retirementSpending * 12);
  const legacyScore = clamp((legacyGap / spendingAnchor) * 35, -25, 30);
  const withdrawalScore = clamp((0.055 - startWithdrawalRate) * 650, -25, 25);
  return clamp(68 + legacyScore + withdrawalScore - shortfallYears * 8, 5, 98);
}

function rothConversionEffectiveStartAge(inputs: ProjectionInputs) {
  return Math.max(inputs.currentAge, inputs.retirementAge, inputs.rothConversionStartAge);
}

function rothConversionEndAge() {
  return 73;
}

function rothConversionDecision(inputs: ProjectionInputs, age: number, taxDeferredBalance: number, portfolioValue: number) {
  const conversionStartAge = rothConversionEffectiveStartAge(inputs);
  const conversionEndAge = rothConversionEndAge();
  const conversionAge = Math.max(age, conversionStartAge);
  const remainingWindowYears = Math.max(0, conversionEndAge - conversionAge);
  const preTaxShare = portfolioValue > 0 ? taxDeferredBalance / portfolioValue : 0;
  const sharePremium = preTaxShare >= 0.45 ? 0.06 : preTaxShare >= 0.25 ? 0.035 : preTaxShare >= 0.15 ? 0.015 : 0;
  const balancePremium = taxDeferredBalance >= 5_000_000 ? 0.04 : taxDeferredBalance >= 2_500_000 ? 0.025 : taxDeferredBalance >= 1_000_000 ? 0.01 : 0;
  const rmdPressurePremium = clamp(Math.max(sharePremium, balancePremium), 0, 0.08);
  const conversionTaxRate = clamp(ordinaryTaxRate(inputs, "taxAware", conversionAge) + stateOrdinaryTaxRate(inputs), 0, 0.95);
  const futurePreTaxRate = clamp(inputs.retirementTaxRate / 100 + stateOrdinaryTaxRate(inputs) + rmdPressurePremium, 0, 0.95);
  const taxEfficiencySpread = futurePreTaxRate - conversionTaxRate;
  const taxEfficiencyFactor = taxEfficiencySpread < -0.02
    ? 0
    : taxEfficiencySpread <= 0.005
      ? 0.35
    : taxEfficiencySpread >= 0.06
      ? 1
      : 0.55 + (taxEfficiencySpread / 0.06) * 0.45;
  const lowBracketYearsRemaining = Math.max(0, Math.min(conversionEndAge, inputs.socialSecurityAge) - conversionAge);
  const windowQualityFactor = remainingWindowYears <= 0
    ? 0
    : lowBracketYearsRemaining > 0
      ? clamp(0.55 + (lowBracketYearsRemaining / remainingWindowYears) * 0.45, 0.55, 1)
      : 0.45;
  const annualPortfolioCap = portfolioValue * (preTaxShare >= 0.45 ? 0.025 : preTaxShare >= 0.25 ? 0.018 : 0.01);
  const annualPreTaxCap = taxDeferredBalance * (preTaxShare >= 0.45 ? 0.09 : preTaxShare >= 0.25 ? 0.065 : 0.045);
  const annualWindowCap = remainingWindowYears > 0 ? taxDeferredBalance / remainingWindowYears : 0;
  const taxEfficientBaseAmount = Math.min(annualPortfolioCap, annualPreTaxCap, annualWindowCap);
  const taxEfficientAmount = age >= conversionStartAge && age < conversionEndAge && taxDeferredBalance > 0
    ? Math.max(0, taxEfficientBaseAmount * taxEfficiencyFactor * windowQualityFactor)
    : 0;
  const amount = inputs.rothConversionBudget > 0
    ? Math.min(inputs.rothConversionBudget, taxEfficientAmount)
    : 0;

  return {
    amount,
    taxEfficientAmount,
    annualPortfolioCap,
    annualPreTaxCap,
    annualWindowCap,
    taxEfficiencyFactor,
    windowQualityFactor,
    taxEfficiencySpread,
    futurePreTaxRate,
    conversionTaxRate,
    rmdPressurePremium
  };
}

function buildSpendingSmileMilestones(inputs: ProjectionInputs): SpendingSmileMilestone[] {
  const safeInputs = normalizeInputs(inputs);
  const retirementHorizon = Math.max(1, safeInputs.lifeExpectancy - safeInputs.retirementAge);
  const anchors = [
    {
      label: "Active years",
      year: 0,
      note: "Lifestyle spending starts from the user-entered retirement spending target."
    },
    {
      label: "Mid-retirement",
      year: Math.round(retirementHorizon * 0.62),
      note: "Discretionary travel and activity spending tapers while the essential floor remains protected."
    },
    {
      label: "Late retirement",
      year: retirementHorizon,
      note: "The model allows a late-life rise for care, housing, or support needs."
    }
  ];

  return anchors.map((anchor) => {
    const annual = retirementSpendingForYear(safeInputs, anchor.year);
    return {
      label: anchor.label,
      age: safeInputs.retirementAge + anchor.year,
      annual,
      monthly: annual / 12,
      realMultiplier: retirementSmileMultiplier(safeInputs, anchor.year),
      note: anchor.note
    };
  });
}

function buildPreRetirementIncomeAnalysis(inputs: ProjectionInputs): PreRetirementIncomeAnalysis {
  const safeInputs = normalizeInputs(inputs);
  const grossAnnualIncome = safeInputs.currentIncome;
  const federalTaxRate = safeInputs.currentTaxRate / 100;
  const stateTaxRate = currentStateOrdinaryTaxRate(safeInputs);
  const blendedTaxRate = clamp(federalTaxRate + stateTaxRate, 0, 0.95);
  const federalTaxes = grossAnnualIncome * federalTaxRate;
  const stateTaxes = grossAnnualIncome * stateTaxRate;
  const annualTaxes = grossAnnualIncome * blendedTaxRate;
  const netAnnualIncome = Math.max(0, grossAnnualIncome - annualTaxes);
  const yearsToRetirement = Math.max(0, safeInputs.retirementAge - safeInputs.currentAge);
  const annualContributions = accountMeta.reduce((total, account) => total + safeInputs.accounts[account.key].contribution, 0);

  return {
    grossAnnualIncome,
    federalTaxRate,
    stateTaxRate,
    blendedTaxRate,
    federalTaxes,
    stateTaxes,
    annualTaxes,
    netAnnualIncome,
    netMonthlyIncome: netAnnualIncome / 12,
    yearsToRetirement,
    totalNetIncomeToRetirement: netAnnualIncome * yearsToRetirement,
    annualContributions,
    availableAfterContributions: netAnnualIncome - annualContributions
  };
}

function buildRothConversionAnalysis(inputs: ProjectionInputs, result: StrategyResult): RothConversionAnalysis {
  const safeInputs = normalizeInputs(inputs);
  const currentPortfolio = totalBalance({
    taxable: safeInputs.accounts.taxable.balance,
    taxDeferred: safeInputs.accounts.taxDeferred.balance,
    roth: safeInputs.accounts.roth.balance,
    cash: safeInputs.accounts.cash.balance
  });
  const firstRetirementRow = result.rows.find((row) => row.age >= safeInputs.retirementAge);
  const retirementPortfolio = Math.max(1, firstRetirementRow?.beginningPortfolio ?? currentPortfolio);
  const conversionStartAge = rothConversionEffectiveStartAge(safeInputs);
  const conversionEndAge = rothConversionEndAge();
  const firstConversionRow = result.rows.find((row) => row.age >= Math.ceil(conversionStartAge));
  const projectedTaxDeferredAtStart = firstConversionRow?.taxDeferredBalance ?? safeInputs.accounts.taxDeferred.balance;
  const projectedPortfolioAtStart = Math.max(1, firstConversionRow?.endingPortfolio ?? retirementPortfolio);
  const preTaxBalance = projectedTaxDeferredAtStart;
  const preTaxShare = projectedPortfolioAtStart > 0 ? preTaxBalance / projectedPortfolioAtStart : 0;
  const lowBracketYears = Math.max(0, Math.min(conversionEndAge, safeInputs.socialSecurityAge) - conversionStartAge);
  const windowYears = Math.max(0, conversionEndAge - conversionStartAge);
  const effectiveConversionTaxRate = clamp(ordinaryTaxRate(safeInputs, "taxAware", conversionStartAge) + stateOrdinaryTaxRate(safeInputs), 0, 0.95);
  const currentBlendedTaxRate = clamp(safeInputs.currentTaxRate / 100 + currentStateOrdinaryTaxRate(safeInputs), 0, 0.95);
  const conversionDecision = rothConversionDecision(safeInputs, conversionStartAge, preTaxBalance, projectedPortfolioAtStart);
  const {
    annualPortfolioCap,
    annualPreTaxCap,
    annualWindowCap,
    taxEfficiencyFactor: taxRateFactor,
    windowQualityFactor,
    taxEfficiencySpread,
    futurePreTaxRate,
    conversionTaxRate,
    rmdPressurePremium,
    amount: modeledRawAnnualConversion,
    taxEfficientAmount: taxEfficientRawAnnualConversion
  } = conversionDecision;
  const modeledAnnualCap = Math.max(0, safeInputs.rothConversionBudget);
  const conversionGuards = [
    { label: "user cap", value: modeledAnnualCap },
    { label: "portfolio guardrail", value: annualPortfolioCap },
    { label: "pre-tax guardrail", value: annualPreTaxCap },
    { label: "window guardrail", value: annualWindowCap }
  ];
  const positiveConversionGuards = conversionGuards.filter((guard) => guard.value > 0);
  const taxEfficientGuards = conversionGuards.filter((guard) => guard.label !== "user cap" && guard.value > 0);
  const limitingGuard = positiveConversionGuards.reduce(
    (lowest, guard) => guard.value < lowest.value ? guard : lowest,
    positiveConversionGuards[0] ?? conversionGuards[0]
  );
  const taxEfficientLimitingGuard = taxEfficientGuards.reduce(
    (lowest, guard) => guard.value < lowest.value ? guard : lowest,
    taxEfficientGuards[0] ?? positiveConversionGuards[0] ?? conversionGuards[0]
  );
  const suggestedAnnualConversion = Math.max(0, Math.round(taxEfficientRawAnnualConversion / 500) * 500);
  const modeledAnnualConversion = Math.max(0, Math.round(modeledRawAnnualConversion / 500) * 500);
  const capLimited = suggestedAnnualConversion > modeledAnnualConversion && modeledAnnualCap > 0;
  const estimatedAnnualTaxFromBrokerage = suggestedAnnualConversion * effectiveConversionTaxRate;
  const totalWindowConversion = suggestedAnnualConversion * windowYears;
  const totalWindowTaxFromBrokerage = estimatedAnnualTaxFromBrokerage * windowYears;
  const brokerageCoverageYears = estimatedAnnualTaxFromBrokerage > 0
    ? safeInputs.accounts.taxable.balance / estimatedAnnualTaxFromBrokerage
    : null;

  let status = "Consider partial";
  if (preTaxBalance <= 0) status = "No pre-tax balance";
  else if (modeledAnnualCap <= 0) status = "Set conversion cap";
  else if (windowYears <= 0) status = "No pre-RMD window";
  else if (suggestedAnnualConversion <= 0) status = "Not priority";
  else if (capLimited) status = "Cap limited";
  else if (preTaxShare >= 0.35 && taxEfficiencySpread >= 0.02) status = "Looks useful";

  const windowCopy = lowBracketYears > 0
    ? `${formatYearCount(lowBracketYears)} low-bracket years from age ${formatAge(conversionStartAge)} before Social Security or RMD pressure`
    : `${formatYearCount(windowYears)} pre-RMD years from age ${formatAge(conversionStartAge)}, but Social Security starts inside or before the window`;
  const coverageCopy = brokerageCoverageYears === null
    ? "No brokerage tax funding is needed at the current setting."
    : `Taxable brokerage covers about ${formatYears(brokerageCoverageYears)} years of estimated conversion taxes.`;
  const reason = modeledAnnualCap <= 0
    ? `Enter an annual conversion ceiling to model exact dollar amounts. Projected tax-deferred assets at conversion start are ${percent(preTaxShare)} of the projected portfolio, and the entered conversion tax rate is about ${percent(effectiveConversionTaxRate)}.`
    : `${percent(preTaxShare)} of the projected portfolio at conversion start is tax-deferred. The model estimates ${currency(projectedTaxDeferredAtStart)} in tax-deferred assets at age ${formatAge(conversionStartAge)}, then compares a ${percent(conversionTaxRate)} conversion tax rate with an estimated ${percent(futurePreTaxRate)} future pre-tax withdrawal/RMD tax rate. ${coverageCopy}`;
  const partialReason = suggestedAnnualConversion <= 0
    ? `A conversion is not prioritized because the current inputs do not show a strong tax-efficient window after age ${formatAge(conversionStartAge)}, or there is no modeled annual conversion cap. This can change if retirement tax rates, state taxes, Social Security age, retirement age, Roth start age, or tax-deferred balances change.`
    : capLimited
      ? `The tax-efficient target is higher than the current modeled cap. The projection will only convert ${currency(modeledAnnualConversion)} per year unless you raise the annual Roth conversion cap, but the tax-deferred balance and RMD pressure support a larger target under these assumptions.`
      : suggestedAnnualConversion < modeledAnnualCap
        ? `Partial is preferred because converting the full ${currency(modeledAnnualCap)} cap may push taxable income too high too quickly or may not be tax-efficient enough. The model trims the amount for bracket control, tax-deferred concentration, pre-RMD years, tax efficiency, and brokerage cash needed to pay conversion tax.`
        : `The modeled amount uses the full annual cap because the tax-deferred balance, tax-efficiency spread, and available pre-RMD window support it under these assumptions.`;
  const amountReason = suggestedAnnualConversion <= 0
    ? `The suggested amount is ${currency(0)} because the model needs a positive conversion cap, available tax-deferred balance, a penalty-aware start age of at least 59.5, and a tax-efficient pre-RMD window before it recommends a conversion.`
    : `The ${currency(suggestedAnnualConversion)} tax-efficient target is based on the projected tax-deferred balance at conversion start, not today's balance or the whole portfolio. It starts with the lowest tax-efficient guardrail, which is the ${taxEfficientLimitingGuard.label} at ${currency(taxEfficientLimitingGuard.value)}, then applies a ${percent(taxRateFactor)} tax-efficiency factor and a ${percent(windowQualityFactor)} window-quality factor. With the current annual cap of ${currency(modeledAnnualCap)}, the projection models ${currency(modeledAnnualConversion)} per year.`;
  const taxFundingReason = estimatedAnnualTaxFromBrokerage <= 0
    ? "No brokerage tax funding is required at the current suggested amount."
    : `At an estimated conversion tax rate of ${percent(effectiveConversionTaxRate)}, the suggested conversion needs about ${currency(estimatedAnnualTaxFromBrokerage)} per year from taxable brokerage. Across the window, that is about ${currency(totalWindowTaxFromBrokerage)}. ${coverageCopy}`;
  const taxEfficiencyReason = `Tax efficiency compares paying about ${percent(conversionTaxRate)} on conversion dollars now versus an estimated ${percent(futurePreTaxRate)} future tax rate on tax-deferred withdrawals. The future rate includes the entered retirement federal/state rates plus a ${percent(rmdPressurePremium)} pre-tax/RMD pressure premium based on how much of the portfolio sits in tax-deferred accounts. The resulting spread is ${percent(taxEfficiencySpread)}.`;
  const windowReason = `${windowCopy}. The model does not convert before age ${formatAge(safeInputs.rothConversionStartAge)} and does not model planned conversions after RMD age ${conversionEndAge}. If the conversion starts after Social Security begins, the window factor is reduced because taxable Social Security can make extra ordinary income less efficient.`;

  return {
    status,
    suggestedAnnualConversion,
    estimatedAnnualTaxFromBrokerage,
    totalWindowConversion,
    totalWindowTaxFromBrokerage,
    windowYears,
    lowBracketYears,
    brokerageCoverageYears,
    effectiveConversionTaxRate,
    currentBlendedTaxRate,
    preTaxShare,
    reason,
    partialReason,
    amountReason,
    taxFundingReason,
    windowReason,
    taxEfficiencyReason,
    limitingFactor: limitingGuard.label,
    conversionStartAge,
    conversionEndAge,
    projectedTaxDeferredAtStart,
    projectedPortfolioAtStart,
    modeledAnnualConversion,
    capLimited,
    modeledAnnualCap,
    annualPortfolioCap,
    annualPreTaxCap,
    annualWindowCap,
    taxRateFactor,
    windowQualityFactor,
    taxEfficiencySpread,
    futurePreTaxRate,
    conversionTaxRate,
    rmdPressurePremium
  };
}

function buildRetirementReturnAnalysis(inputs: ProjectionInputs, result: StrategyResult): RetirementReturnAnalysis {
  const safeInputs = normalizeInputs(inputs);
  const retirementRows = result.rows.filter((row) => row.retired);
  const returnBaseTotal = retirementRows.reduce((total, row) => total + row.returnBase, 0);
  const investmentReturnTotal = retirementRows.reduce((total, row) => total + row.investmentReturn, 0);
  const weightedAverageReturn = returnBaseTotal > 0 ? investmentReturnTotal / returnBaseTotal : 0;
  const firstRetirementRow = retirementRows[0];
  const retirementYears = retirementRows.length;
  const negativeReturnYears = retirementRows.filter((row) => row.portfolioReturnRate < 0).length;
  const averageAnnualInvestmentReturn = retirementYears > 0 ? investmentReturnTotal / retirementYears : 0;
  const normalReturnAssumption = safeInputs.postRetirementReturn / 100;
  const firstRetirementReturn = firstRetirementRow?.portfolioReturnRate ?? 0;
  const firstRetirementInvestmentReturn = firstRetirementRow?.investmentReturn ?? 0;
  const firstCashReturn = Math.min(0.03, Math.max(0.01, (safeInputs.postRetirementReturn + safeInputs.marketShock) / 100 / 3));
  const normalCashReturn = Math.min(0.03, Math.max(0.01, normalReturnAssumption / 3));

  return {
    weightedAverageReturn,
    firstRetirementReturn,
    normalReturnAssumption,
    firstRetirementInvestmentReturn,
    averageAnnualInvestmentReturn,
    negativeReturnYears,
    retirementYears,
    returnReason: `Across ${retirementYears} retirement years, the weighted modeled portfolio return is ${percent(weightedAverageReturn)}. This is weighted by the dollars invested each year, so larger portfolio years matter more than smaller portfolio years. It starts from the user-entered retirement return assumption of ${percent(normalReturnAssumption)}, then reflects the cash sleeve and the first retirement-year shock.`,
    assumptionReason: `The model is not using a fixed 7-8% stock-market return. It uses the user-entered retirement return assumption of ${percent(normalReturnAssumption)} for invested accounts after retirement, models cash at a lower rate of about ${percent(normalCashReturn)}, and applies the first retirement-year shock of ${percent(safeInputs.marketShock / 100)}. A 7-8% input may be reasonable for a more equity-heavy or optimistic scenario, but it can understate sequence risk when withdrawals are starting. If you want that scenario, change the Retirement return assumption here or in Tax and markets and the weighted return will recalculate.`,
    shockReason: `The first retirement year applies the ${percent(normalReturnAssumption)} post-retirement return assumption plus the ${percent(safeInputs.marketShock / 100)} retirement shock. Cash is modeled separately at a lower positive rate, so the blended first-year portfolio return is ${percent(firstRetirementReturn)} and generates ${currency(firstRetirementInvestmentReturn)} before withdrawals and taxes.`,
    calculationReason: `The output uses investment return before spending withdrawals, taxes, RMDs, and Roth conversion movements. Average annual investment return is ${currency(averageAnnualInvestmentReturn)}, with ${negativeReturnYears} negative return years in the retirement projection. In the first retirement year, cash is modeled at about ${percent(firstCashReturn)} instead of the full risky-asset return.`
  };
}

function buildVolatilityGuidance(inputs: ProjectionInputs, result: StrategyResult): VolatilityGuidance {
  const safeInputs = normalizeInputs(inputs);
  const firstRetirementRow = result.rows.find((row) => row.age >= safeInputs.retirementAge);
  const currentPortfolio = totalBalance({
    taxable: safeInputs.accounts.taxable.balance,
    taxDeferred: safeInputs.accounts.taxDeferred.balance,
    roth: safeInputs.accounts.roth.balance,
    cash: safeInputs.accounts.cash.balance
  });
  const retirementPortfolio = Math.max(0, firstRetirementRow?.beginningPortfolio ?? currentPortfolio);
  const stableIncome = firstRetirementRow?.stableIncome ?? safeInputs.pensionAnnual;
  const annualNetWithdrawalNeed = Math.max(0, firstRetirementRow?.withdrawalNeed ?? safeInputs.retirementSpending - stableIncome);
  const essentialNetNeed = Math.max(0, safeInputs.essentialSpending - stableIncome);
  const bucketWithdrawalBase = Math.max(annualNetWithdrawalNeed, essentialNetNeed);
  const cashYears = safeInputs.cashBucketYears;
  const bondYears = safeInputs.bondBucketYears;
  const cashTarget = Math.min(retirementPortfolio, Math.max(bucketWithdrawalBase * cashYears, bucketWithdrawalBase > 0 ? 25000 : 0));
  const defensiveTarget = Math.min(Math.max(0, retirementPortfolio - cashTarget), bucketWithdrawalBase * bondYears);
  const growthTarget = Math.max(0, retirementPortfolio - cashTarget - defensiveTarget);

  return {
    annualNetWithdrawalNeed,
    essentialNetNeed,
    bucketWithdrawalBase,
    cashYears,
    bondYears,
    crisisCoverageYears: cashYears + bondYears,
    buckets: [
      {
        label: "Cash / T-bill bucket",
        location: "Cash, money market, T-bills",
        target: cashTarget,
        current: safeInputs.accounts.cash.balance,
        status: "Current cash",
        guidance: reserveDeltaCopy(safeInputs.accounts.cash.balance, cashTarget, "cash reserve"),
        examples: ["Checking / savings", "Treasury bills", "money market fund", "3-12 month T-bill ladder"]
      },
      {
        label: "Bond bucket",
        location: "Treasuries, TIPS, CDs, high-quality bonds, or bond ladder",
        target: defensiveTarget,
        current: safeInputs.accounts.taxable.balance,
        status: "Flexible taxable balance",
        guidance: `Earmark roughly ${formatYears(bondYears)} years of net withdrawals here after cash is used, before selling stocks in a prolonged drawdown.`,
        examples: ["Treasury ladder", "TIPS ladder", "CD ladder", "short/intermediate high-quality bond fund"]
      },
      {
        label: "Stock growth bucket",
        location: "Diversified equities in Roth plus remaining taxable and pre-tax accounts",
        target: growthTarget,
        current: null,
        status: "Remainder after reserves",
        guidance: `Keep this bucket invested for the long horizon. With the current inputs, cash plus bonds are designed to cover about ${formatYears(cashYears + bondYears)} years before forced stock sales.`,
        examples: ["U.S. total market index", "international equity index", "Roth growth sleeve", "tax-efficient equity ETFs"]
      }
    ]
  };
}

function reserveDeltaCopy(current: number, target: number, label: string) {
  const delta = current - target;
  if (delta >= 0) return `The ${label} is above target by ${currency(delta)}, so near-term withdrawals can avoid growth sales.`;
  return `Add or earmark ${currency(Math.abs(delta))} to reach the target before relying on long-term growth assets.`;
}

function formatYears(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 10) return "10+";
  return value.toFixed(value >= 2 ? 0 : 1);
}

function formatYearCount(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0";
  return Number.isInteger(value) ? `${value}` : value.toFixed(1);
}

function formatAge(value: number) {
  if (!Number.isFinite(value)) return "0";
  return Number.isInteger(value) ? `${value}` : value.toFixed(1);
}

function totalBalance(balances: BalanceSet) {
  return balances.taxable + balances.taxDeferred + balances.roth + balances.cash;
}

function compactCurrency(value: number) {
  if (Math.abs(value) >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (Math.abs(value) >= 1000) return `$${Math.round(value / 1000)}K`;
  return `$${Math.round(value)}`;
}

function stateLabel(value: string) {
  return stateOptions.find((state) => state.value === value)?.label ?? value;
}

function confidenceLabel(score: number) {
  if (score >= 82) return "Strong";
  if (score >= 68) return "Workable";
  if (score >= 50) return "Fragile";
  return "Needs adjustment";
}

function spendingModelLabel(model: SpendingModel) {
  return model === "retirementSmile" ? "Natural spending smile" : "Flat real spending";
}

function guardrailCopy(action: StrategyResult["guardrailAction"]) {
  if (action === "raise") return "Raise is available";
  if (action === "reduce") return "Reduction is triggered";
  return "Hold current spending";
}

function clamp(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}
