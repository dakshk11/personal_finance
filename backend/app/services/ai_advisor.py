from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken


AI_ADVISOR_MODELS = ("gpt-5.5", "gpt-5.4", "gpt-5.4-mini")
AIAdvisorModel = Literal["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"]


class AIAdvisorConfigurationError(RuntimeError):
    pass


class AIAdvisorProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RetirementPromptField:
    id: str
    label: str
    placeholder: str


@dataclass(frozen=True)
class RetirementPromptModule:
    id: str
    title: str
    prompt: str
    fields: tuple[RetirementPromptField, ...]


RETIREMENT_PROMPT_MODULES: tuple[RetirementPromptModule, ...] = (
    RetirementPromptModule(
        id="full-retirement-blueprint",
        title="Full Retirement Blueprint",
        prompt=(
            "Act as a certified financial planner with 25 years of experience specializing in retirement planning. "
            "I am [age] years old, earning $[income] per year, with $[current savings] saved so far. I plan to retire at [retirement age] and want a monthly income of $[target monthly income] in retirement. "
            "My current accounts include [list: 401k, IRA, brokerage, etc.] with the following balances [balances]. My employer matches [match %] on my 401k up to [limit]. "
            "I have [number] dependents and my monthly expenses are $[amount]. Build me a complete, step-by-step retirement blueprint that covers: how much I need to save each month to hit my goal, which accounts to prioritize and in what order, how to think about Social Security timing, how inflation affects my target number, and what my portfolio should look like at each decade of my life between now and retirement. "
            "Be specific with numbers, percentages, and timelines. Treat me like a serious client, not a beginner."
        ),
        fields=(
            RetirementPromptField("age", "Current age", "[age]"),
            RetirementPromptField("income", "Annual income", "[income]"),
            RetirementPromptField("current_savings", "Current savings", "[current savings]"),
            RetirementPromptField("retirement_age", "Retirement age", "[retirement age]"),
            RetirementPromptField("target_monthly_income", "Target monthly retirement income", "[target monthly income]"),
            RetirementPromptField("account_list", "Current accounts", "[list: 401k, IRA, brokerage, etc.]"),
            RetirementPromptField("account_balances", "Account balances", "[balances]"),
            RetirementPromptField("employer_match_percent", "Employer 401k match percent", "[match %]"),
            RetirementPromptField("employer_match_limit", "Employer match limit", "[limit]"),
            RetirementPromptField("dependents", "Number of dependents", "[number]"),
            RetirementPromptField("monthly_expenses", "Monthly expenses", "[amount]"),
        ),
    ),
    RetirementPromptModule(
        id="tax-optimization",
        title="Tax Optimization",
        prompt=(
            "Act as a senior tax strategist who specializes in retirement and wealth planning for high-income earners. "
            "My situation is as follows: I earn $[gross income] per year from [salary / freelance / business / investments]. My current tax bracket is [bracket]. "
            "I contribute $[amount] to my 401k and $[amount] to an IRA. I also have [any other accounts or assets]. My state of residence is [state]. "
            "I am [age] years old and plan to retire at [age]. Given this, build me a complete tax optimization strategy for retirement that covers: whether I should be doing traditional or Roth contributions right now and why, how to use a Roth conversion ladder to minimize taxes in retirement, whether a backdoor Roth makes sense for my income level, how to sequence withdrawals from my accounts in retirement to pay the least possible tax, and any tax-advantaged accounts or strategies I am likely missing. "
            "Give me a specific, prioritized action plan I can start implementing this year."
        ),
        fields=(
            RetirementPromptField("gross_income", "Gross annual income", "[gross income]"),
            RetirementPromptField("income_source", "Income source", "[salary / freelance / business / investments]"),
            RetirementPromptField("tax_bracket", "Current tax bracket", "[bracket]"),
            RetirementPromptField("k401_contribution", "401k contribution", "[amount]"),
            RetirementPromptField("ira_contribution", "IRA contribution", "[amount]"),
            RetirementPromptField("other_accounts_assets", "Other accounts or assets", "[any other accounts or assets]"),
            RetirementPromptField("state", "State of residence", "[state]"),
            RetirementPromptField("age", "Current age", "[age]"),
            RetirementPromptField("retirement_age", "Retirement age", "[age]"),
        ),
    ),
    RetirementPromptModule(
        id="portfolio-strategy",
        title="Portfolio Strategy",
        prompt=(
            "Act as a portfolio strategist with deep expertise in retirement investing and long-term asset allocation. "
            "I am [age] years old with a retirement target of age [retirement age]. My current portfolio is allocated as follows: [list your current holdings and percentages]. "
            "My total investable assets are $[amount]. My risk tolerance is [conservative / moderate / aggressive] and here is why: [brief explanation of your comfort with volatility]. "
            "I have a monthly contribution of $[amount] going into my accounts. Using modern portfolio theory and lifecycle investing principles, do the following for me: critique my current allocation and tell me exactly what is wrong with it, build me a target allocation by asset class that is appropriate for my age and goals, show me how that allocation should shift every 5 years between now and retirement, recommend specific low-cost index funds or ETFs for each asset class with their ticker symbols and expense ratios, and tell me how often I should rebalance and exactly how to do it. "
            "Be direct and specific. Do not give me generic advice."
        ),
        fields=(
            RetirementPromptField("age", "Current age", "[age]"),
            RetirementPromptField("retirement_age", "Retirement age", "[retirement age]"),
            RetirementPromptField("holdings_allocation", "Current holdings and percentages", "[list your current holdings and percentages]"),
            RetirementPromptField("investable_assets", "Total investable assets", "[amount]"),
            RetirementPromptField("risk_tolerance", "Risk tolerance", "[conservative / moderate / aggressive]"),
            RetirementPromptField("risk_explanation", "Comfort with volatility", "[brief explanation of your comfort with volatility]"),
            RetirementPromptField("monthly_contribution", "Monthly contribution", "[amount]"),
        ),
    ),
    RetirementPromptModule(
        id="risk-stress-test",
        title="Retirement Risk Stress Test",
        prompt=(
            "Act as a retirement risk analyst and fiduciary advisor. I am planning to retire at age [age] with a portfolio of $[amount]. "
            "I plan to withdraw $[monthly amount] per month to cover my expenses in retirement, which I expect to last [number] years. My portfolio is currently allocated [allocation breakdown]. "
            "I am relying on Social Security starting at age [age] for an estimated $[monthly amount] per month. Run a complete retirement risk stress test on my plan that covers the following scenarios: What happens to my portfolio if the market drops 40% in my first year of retirement, which is called sequence of returns risk, and how do I protect against it. "
            "Whether my withdrawal rate is safe based on the 4% rule and its limitations, and what a more conservative safe withdrawal rate looks like for my situation. How long my money actually lasts under three scenarios, a good market environment, an average one, and a bad one. "
            "What the real impact of inflation at 3%, 4%, and 5% does to my purchasing power over 30 years. And what specific guardrails, buffer strategies, or income floors I should put in place to make sure I never run out of money. "
            "Give me a specific risk mitigation plan, not just a diagnosis."
        ),
        fields=(
            RetirementPromptField("retirement_age", "Retirement age", "[age]"),
            RetirementPromptField("portfolio_amount", "Portfolio amount", "[amount]"),
            RetirementPromptField("monthly_withdrawal", "Monthly withdrawal", "[monthly amount]"),
            RetirementPromptField("retirement_years", "Expected retirement years", "[number]"),
            RetirementPromptField("allocation_breakdown", "Allocation breakdown", "[allocation breakdown]"),
            RetirementPromptField("social_security_age", "Social Security start age", "[age]"),
            RetirementPromptField("social_security_monthly", "Monthly Social Security", "[monthly amount]"),
        ),
    ),
    RetirementPromptModule(
        id="social-security-optimization",
        title="Social Security Optimization",
        prompt=(
            "Act as a Social Security optimization specialist and retirement income strategist. Here is my situation: I am [age] years old. My spouse is [age] years old. "
            "My estimated Social Security benefit at age 62 is $[amount], at full retirement age of [FRA age] is $[amount], and at age 70 is $[amount]. "
            "My spouse's estimated benefit at 62 is $[amount], at FRA is $[amount], and at 70 is $[amount]. My current health is [good / average / below average] and my family longevity history is [brief description]. "
            "We have $[portfolio amount] saved and plan to retire at [age]. We have [other income sources if any]. Given all of this, do the following: Calculate the break-even age for each claiming strategy, meaning at what age I come out ahead by waiting versus claiming early. "
            "Model the three most common claiming strategies for a married couple, one spouse claims early and one delays, both delay to 70, and both claim at FRA, and show me the lifetime income difference between them. Tell me which strategy maximizes our combined lifetime Social Security income based on our ages and health. "
            "Explain exactly how the spousal benefit works and whether my spouse should claim on their own record or mine. And show me how Social Security fits into our overall retirement income plan alongside our portfolio withdrawals. Be specific with dollar amounts and timelines."
        ),
        fields=(
            RetirementPromptField("age", "Current age", "[age]"),
            RetirementPromptField("spouse_age", "Spouse age", "[age]"),
            RetirementPromptField("benefit_62", "Your benefit at 62", "[amount]"),
            RetirementPromptField("fra_age", "Your full retirement age", "[FRA age]"),
            RetirementPromptField("benefit_fra", "Your benefit at FRA", "[amount]"),
            RetirementPromptField("benefit_70", "Your benefit at 70", "[amount]"),
            RetirementPromptField("spouse_benefit_62", "Spouse benefit at 62", "[amount]"),
            RetirementPromptField("spouse_benefit_fra", "Spouse benefit at FRA", "[amount]"),
            RetirementPromptField("spouse_benefit_70", "Spouse benefit at 70", "[amount]"),
            RetirementPromptField("health", "Current health", "[good / average / below average]"),
            RetirementPromptField("longevity_history", "Family longevity history", "[brief description]"),
            RetirementPromptField("portfolio_amount", "Portfolio amount saved", "[portfolio amount]"),
            RetirementPromptField("retirement_age", "Retirement age", "[age]"),
            RetirementPromptField("other_income", "Other income sources", "[other income sources if any]"),
        ),
    ),
)

RETIREMENT_PROMPT_MODULE_BY_ID = {module.id: module for module in RETIREMENT_PROMPT_MODULES}


def valid_ai_advisor_model(model: str) -> bool:
    return model in AI_ADVISOR_MODELS


def get_retirement_prompt_module(module_id: str) -> RetirementPromptModule | None:
    return RETIREMENT_PROMPT_MODULE_BY_ID.get(module_id)


def required_field_ids(module: RetirementPromptModule) -> list[str]:
    return [field.id for field in module.fields]


def missing_required_fields(module: RetirementPromptModule, inputs: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in module.fields:
        value = inputs.get(field.id)
        if value is None or str(value).strip() == "":
            missing.append(field.id)
    return missing


def sanitized_inputs(module: RetirementPromptModule, inputs: dict[str, Any]) -> dict[str, str]:
    return {field.id: str(inputs.get(field.id, "")).strip() for field in module.fields}


def build_retirement_prompt(module: RetirementPromptModule, inputs: dict[str, Any]) -> str:
    values = sanitized_inputs(module, inputs)
    prompt = module.prompt
    for field in module.fields:
        prompt = _replace_first(prompt, field.placeholder, values[field.id])
    return prompt


def encrypt_api_key(api_key: str, secret: str) -> str:
    return _fernet(secret).encrypt(api_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(ciphertext: str, secret: str) -> str:
    try:
        return _fernet(secret).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AIAdvisorConfigurationError("Stored OpenAI API key could not be decrypted.") from exc


def api_key_fingerprint(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def validate_openai_api_key(api_key: str) -> None:
    _openai_json_request("https://api.openai.com/v1/models", api_key, method="GET")


def create_openai_response(api_key: str, model: str, prompt: str) -> tuple[str, dict[str, Any]]:
    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": 5000,
    }
    response = _openai_json_request("https://api.openai.com/v1/responses", api_key, method="POST", payload=payload)
    return _extract_response_text(response), response


def response_usage(response_payload: dict[str, Any]) -> dict[str, Any]:
    usage = response_payload.get("usage")
    return usage if isinstance(usage, dict) else {}


def now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _fernet(secret: str) -> Fernet:
    normalized = secret.strip()
    if len(normalized) < 32:
        raise AIAdvisorConfigurationError("AI advisor encryption secret must be at least 32 characters.")
    key = urlsafe_b64encode(hashlib.sha256(normalized.encode("utf-8")).digest())
    return Fernet(key)


def _replace_first(value: str, old: str, new: str) -> str:
    index = value.find(old)
    if index < 0:
        return value
    return f"{value[:index]}{new}{value[index + len(old):]}"


def _openai_json_request(
    url: str,
    api_key: str,
    *,
    method: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    except HTTPError as exc:
        message = _provider_error_message(exc)
        status_code = 400 if exc.code in {401, 403} else 502
        raise AIAdvisorProviderError(message, status_code=status_code) from exc
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise AIAdvisorProviderError("OpenAI request failed. Please try again later.", status_code=502) from exc


def _provider_error_message(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8", errors="ignore") or "{}")
    except json.JSONDecodeError:
        return "OpenAI request failed."
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    return "OpenAI request failed."


def _extract_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
    if parts:
        return "\n\n".join(parts)
    raise AIAdvisorProviderError("OpenAI response did not include report text.", status_code=502)
