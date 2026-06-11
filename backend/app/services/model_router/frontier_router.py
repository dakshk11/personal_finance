"""
Routes prompts to the best frontier model (Claude, GPT, OpenAI reasoning)
based on benchmark data and user constraints.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .benchmark_db import BenchmarkDB
from .task_classifier import TaskClassifier, TaskProfile


Provider = Literal["anthropic", "openai", "any"]
CostPreference = Literal["economy", "balanced", "performance", "best"]


@dataclass
class FrontierRoutingDecision:
    model: str
    provider: str
    display_name: str
    task_type: str
    complexity: str
    score: float
    cost_per_1m_input: float
    cost_per_1m_output: float
    thinking_mode: Optional[str]
    reason: str
    alternatives: list[dict]


# Maps complexity + task to recommended thinking mode for reasoning models
_THINKING_MODE_MAP = {
    ("simple", "math"): "low",
    ("moderate", "math"): "medium",
    ("hard", "math"): "high",
    ("expert", "math"): "high",
    ("simple", "reasoning"): "low",
    ("moderate", "reasoning"): "medium",
    ("hard", "reasoning"): "high",
    ("expert", "reasoning"): "high",
    ("expert", "science"): "high",
    ("hard", "science"): "medium",
    ("expert", "coding"): "medium",
}


class FrontierRouter:
    """
    Routes prompts to the best frontier API model.
    Understands Claude (Opus/Sonnet/Haiku) and OpenAI (GPT-4.1, o-series).
    """

    def __init__(self, db: Optional[BenchmarkDB] = None):
        self.db = db or BenchmarkDB()
        self.classifier = TaskClassifier()

    def route(
        self,
        prompt: str,
        provider: Provider = "any",
        cost_preference: CostPreference = "balanced",
        max_cost_per_1m_input: Optional[float] = None,
        require_thinking: bool = False,
    ) -> FrontierRoutingDecision:
        """
        Select the best frontier model for the prompt.

        Args:
            prompt: The user's prompt.
            provider: Restrict to 'anthropic', 'openai', or 'any'.
            cost_preference: 'economy' | 'balanced' | 'performance' | 'best'
            max_cost_per_1m_input: Hard cost ceiling in $/1M tokens.
            require_thinking: Force a model with extended thinking / reasoning mode.
        """
        profile = self.classifier.classify(prompt)
        all_models = self.db.all_frontier_models()

        candidates = self._filter_candidates(
            all_models, provider, cost_preference, max_cost_per_1m_input, require_thinking
        )
        scored = self._score_candidates(candidates, profile, cost_preference)

        if not scored:
            # Safety fallback
            fallback_id = "claude-sonnet-4-6" if provider != "openai" else "gpt-4.1"
            fallback = all_models.get(fallback_id, list(all_models.values())[0])
            return FrontierRoutingDecision(
                model=fallback_id,
                provider=fallback["provider"],
                display_name=fallback["display_name"],
                task_type=profile.task_type,
                complexity=profile.complexity,
                score=0.0,
                cost_per_1m_input=fallback["cost_per_1m_input"],
                cost_per_1m_output=fallback["cost_per_1m_output"],
                thinking_mode=None,
                reason="Fallback — no candidates matched filters.",
                alternatives=[],
            )

        best = scored[0]
        thinking_mode = self._recommend_thinking_mode(
            best["model_id"], best["model_data"], profile
        )
        reason = self._explain(best["model_id"], best["model_data"], profile, best["final_score"], cost_preference, thinking_mode)

        alternatives = []
        for a in scored[1:4]:
            alt_thinking = self._recommend_thinking_mode(a["model_id"], a["model_data"], profile)
            alternatives.append(
                {
                    "model": a["model_id"],
                    "provider": a["model_data"]["provider"],
                    "display_name": a["model_data"]["display_name"],
                    "score": a["final_score"],
                    "cost_per_1m_input": a["model_data"]["cost_per_1m_input"],
                    "thinking_mode": alt_thinking,
                }
            )

        return FrontierRoutingDecision(
            model=best["model_id"],
            provider=best["model_data"]["provider"],
            display_name=best["model_data"]["display_name"],
            task_type=profile.task_type,
            complexity=profile.complexity,
            score=best["final_score"],
            cost_per_1m_input=best["model_data"]["cost_per_1m_input"],
            cost_per_1m_output=best["model_data"]["cost_per_1m_output"],
            thinking_mode=thinking_mode,
            reason=reason,
            alternatives=alternatives,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _filter_candidates(
        self,
        models: dict,
        provider: Provider,
        cost_preference: CostPreference,
        max_cost: Optional[float],
        require_thinking: bool,
    ) -> dict:
        # Cost ceilings per preference ($/1M input tokens)
        cost_ceiling = {
            "economy": 1.0,
            "balanced": 5.0,
            "performance": 20.0,
            "best": 999.0,
        }[cost_preference]

        if max_cost is not None:
            cost_ceiling = min(cost_ceiling, max_cost)

        result = {}
        for mid, mdata in models.items():
            if provider != "any" and mdata["provider"] != provider:
                continue
            if mdata["cost_per_1m_input"] > cost_ceiling:
                continue
            if require_thinking and "extended" not in mdata.get("thinking_modes", []) and "high" not in mdata.get("thinking_modes", []):
                continue
            result[mid] = mdata

        return result

    def _score_candidates(
        self, candidates: dict, profile: TaskProfile, cost_preference: CostPreference
    ) -> list[dict]:
        results = []

        for mid, mdata in candidates.items():
            base_score = self.db.task_score(mdata, profile.task_type)
            strength_mult = self.db.strength_match(mdata, profile.task_type)
            perf_score = base_score * strength_mult

            # Complexity alignment: penalize overkill for simple tasks and underpowered for hard
            tier = mdata.get("tier", "balanced")
            complexity_fit = self._complexity_fit_score(tier, profile.complexity)

            # Cost efficiency factor
            cost_factor = self._cost_efficiency(mdata["cost_per_1m_input"], cost_preference)

            final_score = perf_score * 0.65 + complexity_fit * 0.25 + cost_factor * 0.10

            results.append(
                {
                    "model_id": mid,
                    "model_data": mdata,
                    "base_score": base_score,
                    "final_score": round(final_score, 2),
                }
            )

        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results

    def _complexity_fit_score(self, tier: str, complexity: str) -> float:
        """How well does the model tier match the task complexity? 0-100."""
        fit_matrix = {
            #              simple  moderate  hard  expert
            "economy":     [95,    60,       20,    5],
            "fast":        [90,    70,       30,    10],
            "balanced":    [75,    95,       75,    55],
            "reasoning":   [50,    80,       98,    95],
            "ultra":       [60,    85,       98,    99],
            "ultra_reasoning": [40, 70,      97,   100],
        }
        idx = {"simple": 0, "moderate": 1, "hard": 2, "expert": 3}.get(complexity, 1)
        row = fit_matrix.get(tier, fit_matrix["balanced"])
        return row[idx]

    def _cost_efficiency(self, cost: float, preference: CostPreference) -> float:
        """Score for how cost-efficient the model is given the preference. 0-100."""
        if preference == "economy":
            return max(0, 100 - cost * 50)
        elif preference == "balanced":
            return max(0, 100 - cost * 10)
        elif preference == "performance":
            return 50  # cost is not a primary concern
        else:  # best
            return 50  # pure performance, ignore cost

    def _recommend_thinking_mode(
        self, model_id: str, model_data: dict, profile: TaskProfile
    ) -> Optional[str]:
        modes = model_data.get("thinking_modes", ["standard"])
        if len(modes) == 1:
            return modes[0]

        key = (profile.complexity, profile.task_type)
        recommended = _THINKING_MODE_MAP.get(key)
        if recommended and recommended in modes:
            return recommended

        # Default: extended/high for hard+ tasks, standard otherwise
        if profile.complexity in ("hard", "expert"):
            for m in ("extended", "high"):
                if m in modes:
                    return m
        return "standard"

    def _explain(
        self,
        model_id: str,
        model_data: dict,
        profile: TaskProfile,
        score: float,
        cost_preference: CostPreference,
        thinking_mode: Optional[str],
    ) -> str:
        name = model_data["display_name"]
        cost_in = model_data["cost_per_1m_input"]
        cost_out = model_data["cost_per_1m_output"]
        strengths = ", ".join(model_data.get("strengths", [])[:3])
        bench_score = self.db.task_score(model_data, profile.task_type)

        parts = [
            f"Selected {name} (score {score:.1f}) for '{profile.task_type}' task at '{profile.complexity}' complexity.",
            f"Benchmark on {profile.task_type}: {bench_score:.1f}/100.",
            f"Cost: ${cost_in}/1M input, ${cost_out}/1M output. Cost preference: {cost_preference}.",
            f"Key strengths: {strengths}.",
        ]
        if thinking_mode and thinking_mode != "standard":
            parts.append(f"Recommended thinking mode: {thinking_mode}.")

        return " ".join(parts)
