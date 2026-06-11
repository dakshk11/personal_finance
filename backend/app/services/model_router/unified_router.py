"""
Unified router — combines Ollama and frontier routing under one interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Union

from .benchmark_db import BenchmarkDB
from .frontier_router import FrontierRoutingDecision, FrontierRouter
from .ollama_router import OllamaRoutingDecision, OllamaRouter
from .task_classifier import TaskClassifier


RouterMode = Literal["local", "frontier", "auto"]


@dataclass
class UnifiedRoutingDecision:
    mode: str  # "local" | "frontier"
    decision: Union[OllamaRoutingDecision, FrontierRoutingDecision]

    @property
    def model(self) -> str:
        return self.decision.model

    @property
    def display_name(self) -> str:
        return self.decision.display_name

    @property
    def reason(self) -> str:
        return self.decision.reason

    @property
    def task_type(self) -> str:
        return self.decision.task_type

    @property
    def complexity(self) -> str:
        return self.decision.complexity

    def summary(self) -> str:
        d = self.decision
        lines = [
            f"Mode:        {self.mode}",
            f"Model:       {d.display_name}  ({d.model})",
            f"Task:        {d.task_type}  [{d.complexity}]",
            f"Score:       {d.score:.1f}",
        ]
        if isinstance(d, FrontierRoutingDecision):
            lines.append(f"Provider:    {d.provider}")
            lines.append(f"Cost:        ${d.cost_per_1m_input}/1M in · ${d.cost_per_1m_output}/1M out")
            if d.thinking_mode and d.thinking_mode != "standard":
                lines.append(f"Thinking:    {d.thinking_mode}")
        lines.append(f"Reason:      {d.reason}")
        if d.alternatives:
            lines.append("Alternatives:")
            for a in d.alternatives[:3]:
                name = a.get("display_name", a.get("model", ""))
                score = a.get("score", 0)
                lines.append(f"  - {name} (score {score:.1f})")
        return "\n".join(lines)


class UnifiedRouter:
    """
    Single entry point for model routing.

    Usage:
        router = UnifiedRouter()
        result = router.route("Write a quicksort in Python")
        print(result.summary())
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db = BenchmarkDB(db_path)
        self.classifier = TaskClassifier()
        self.ollama = OllamaRouter(self.db)
        self.frontier = FrontierRouter(self.db)

    def route(
        self,
        prompt: str,
        mode: RouterMode = "auto",
        # Frontier options
        provider: str = "any",
        cost_preference: str = "balanced",
        max_cost_per_1m_input: Optional[float] = None,
        require_thinking: bool = False,
        # Local options
        available_local_models: Optional[list[str]] = None,
        prefer_fast: bool = False,
        min_vram_gb: Optional[float] = None,
    ) -> UnifiedRoutingDecision:
        """
        Route a prompt to the best model.

        mode='auto': Try local first; if no good local match or task is expert-level, use frontier.
        mode='local': Only use local Ollama models.
        mode='frontier': Only use frontier API models.
        """
        if mode == "local":
            decision = self.ollama.route(
                prompt,
                available_models=available_local_models,
                prefer_fast=prefer_fast,
                min_vram_gb=min_vram_gb,
            )
            return UnifiedRoutingDecision(mode="local", decision=decision)

        if mode == "frontier":
            decision = self.frontier.route(
                prompt,
                provider=provider,
                cost_preference=cost_preference,
                max_cost_per_1m_input=max_cost_per_1m_input,
                require_thinking=require_thinking,
            )
            return UnifiedRoutingDecision(mode="frontier", decision=decision)

        # Auto mode: pick local if a strong local model is available
        profile = self.classifier.classify(prompt)
        # Treat empty list as "no local models" — only auto-discover when None
        local_models = (
            self.ollama.list_local_models()
            if available_local_models is None
            else available_local_models
        )

        if local_models:
            local_decision = self.ollama.route(
                prompt,
                available_models=local_models,
                prefer_fast=prefer_fast,
                min_vram_gb=min_vram_gb,
            )
            # Use local if: score is good enough and complexity is not expert
            local_adequate = (
                local_decision.score >= 60
                and profile.complexity != "expert"
                and not require_thinking
            )
            if local_adequate:
                return UnifiedRoutingDecision(mode="local", decision=local_decision)

        # Fall through to frontier
        frontier_decision = self.frontier.route(
            prompt,
            provider=provider,
            cost_preference=cost_preference,
            max_cost_per_1m_input=max_cost_per_1m_input,
            require_thinking=require_thinking,
        )
        return UnifiedRoutingDecision(mode="frontier", decision=frontier_decision)

    def explain_all(
        self,
        prompt: str,
        top_n: int = 5,
        available_local_models: Optional[list[str]] = None,
    ) -> str:
        """
        Returns a ranked table of ALL models (local + frontier) for a prompt.
        Useful for transparency and debugging.
        """
        profile = self.classifier.classify(prompt)
        local_models = available_local_models or self.ollama.list_local_models()

        lines = [
            f"Prompt analysis:",
            f"  Task type:   {profile.task_type}",
            f"  Complexity:  {profile.complexity}",
            f"  Long ctx:    {profile.requires_long_context}",
            f"  Keywords:    {', '.join(profile.keywords[:5])}",
            "",
        ]

        # Frontier
        lines.append("=== Frontier Models (top 5) ===")
        frontier_all = self.db.all_frontier_models()
        frontier_scored = []
        for mid, mdata in frontier_all.items():
            score = self.db.task_score(mdata, profile.task_type)
            mult = self.db.strength_match(mdata, profile.task_type)
            frontier_scored.append((mid, mdata, score * mult))
        frontier_scored.sort(key=lambda x: x[2], reverse=True)

        for mid, mdata, score in frontier_scored[:top_n]:
            thinking = ""
            modes = mdata.get("thinking_modes", ["standard"])
            if len(modes) > 1 and profile.complexity in ("hard", "expert"):
                thinking = f"  [thinking: {'extended' if 'extended' in modes else 'high'}]"
            lines.append(
                f"  {mdata['display_name']:<30} score={score:5.1f}  "
                f"${mdata['cost_per_1m_input']}/1M in{thinking}"
            )

        # Local
        if local_models:
            lines.append("")
            lines.append("=== Local Ollama Models (available) ===")
            local_scored = self.ollama._score_models(profile, local_models, False, None)
            for entry in local_scored[:top_n]:
                name = entry["model_data"].get("display_name", entry["model_id"])
                lines.append(
                    f"  {name:<30} score={entry['final_score']:5.1f}  [{entry['model_id']}]"
                )
        else:
            lines.append("")
            lines.append("=== Local Ollama Models ===")
            lines.append("  (no Ollama models found — run `ollama list` to check)")

        return "\n".join(lines)
