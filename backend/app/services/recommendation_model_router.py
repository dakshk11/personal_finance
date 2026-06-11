from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Literal

from app.services.model_router import UnifiedRouter
from app.services.model_router.frontier_router import FrontierRoutingDecision


RecommendationModelMode = Literal["ollama", "foundation"]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecommendationModelDecision:
    model: str
    display_name: str
    mode: RecommendationModelMode
    reason: str
    metadata: dict[str, object]


class RecommendationModelRouter:
    def __init__(self) -> None:
        self.router = UnifiedRouter()

    def route(
        self,
        prompt: str,
        mode: RecommendationModelMode,
        ollama_base_url: str | None = None,
        *,
        prefer_fast_local: bool = False,
    ) -> RecommendationModelDecision:
        if mode == "ollama":
            decision = self.router.route(prompt, mode="local")
            model = decision.model
            display_name = decision.display_name
            reason = decision.reason
            if self._should_use_faster_local_model(model, decision.task_type, prefer_fast_local):
                for alternative in decision.decision.alternatives:
                    alt_model = str(alternative.get("model", ""))
                    if alt_model and not self._is_reasoning_local_model(alt_model):
                        model = alt_model
                        display_name = str(alternative.get("display_name") or alt_model)
                        reason = (
                            f"Selected {display_name} as a faster local model for this "
                            f"{decision.task_type} workflow. {decision.reason}"
                        )
                        break
            logger.info(
                "Model router selected local Ollama model %s (%s): %s",
                display_name,
                model,
                reason,
            )
            return RecommendationModelDecision(
                model=f"ollama:{model}",
                display_name=display_name,
                mode="ollama",
                reason=reason,
                metadata={
                    "task_type": decision.task_type,
                    "complexity": decision.complexity,
                    "score": decision.decision.score,
                    "available_models": getattr(decision.decision, "available_models", []),
                    "ollama_base_url": ollama_base_url,
                    "alternatives": decision.decision.alternatives,
                },
            )

        decision = self.router.route(prompt, mode="frontier", provider="openai", cost_preference="balanced")
        routed = decision.decision
        app_model = self._openai_model_for_app(routed)
        logger.info(
            "Model router selected foundation model %s (%s routed from %s): %s",
            decision.display_name,
            app_model,
            routed.model,
            decision.reason,
        )
        return RecommendationModelDecision(
            model=app_model,
            display_name=decision.display_name,
            mode="foundation",
            reason=decision.reason,
            metadata={
                "task_type": decision.task_type,
                "complexity": decision.complexity,
                "score": routed.score,
                "provider": routed.provider,
                "thinking_mode": routed.thinking_mode,
                "alternatives": routed.alternatives,
            },
        )

    def _openai_model_for_app(self, decision: FrontierRoutingDecision) -> str:
        if decision.model in {"gpt-5.5", "gpt-5.4", "gpt-5.4-mini"}:
            return decision.model
        if decision.complexity in {"hard", "expert"} or decision.thinking_mode in {"high", "extended"}:
            return "gpt-5.5"
        if decision.complexity == "simple":
            return "gpt-5.4-mini"
        return "gpt-5.4"

    def _should_use_faster_local_model(self, model: str, task_type: str, prefer_fast_local: bool) -> bool:
        return self._is_reasoning_local_model(model) and (prefer_fast_local or task_type not in {"coding", "math", "reasoning", "science"})

    def _is_reasoning_local_model(self, model: str) -> bool:
        return "deepseek-r1" in model.lower()
