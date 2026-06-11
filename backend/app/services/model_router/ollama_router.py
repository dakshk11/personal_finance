"""
Routes prompts to the best available local Ollama model based on
benchmark scores and task classification.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional

from .benchmark_db import BenchmarkDB
from .hardware_detector import HardwareDetector, HardwareProfile
from .task_classifier import TaskClassifier, TaskProfile


@dataclass
class OllamaRoutingDecision:
    model: str
    display_name: str
    task_type: str
    complexity: str
    score: float
    reason: str
    alternatives: list[dict]
    available_models: list[str]


class OllamaRouter:
    """
    Discovers locally installed Ollama models, then picks the best one
    for the given prompt using benchmark data and local hardware specs.
    """

    def __init__(self, db: Optional[BenchmarkDB] = None):
        self.db = db or BenchmarkDB()
        self.classifier = TaskClassifier()
        self._hw: Optional[HardwareProfile] = None  # lazy-loaded

    def hardware(self) -> HardwareProfile:
        """Detect (and cache) local hardware specs."""
        if self._hw is None:
            self._hw = HardwareDetector().detect()
        return self._hw

    # ------------------------------------------------------------------ #
    # Model discovery
    # ------------------------------------------------------------------ #

    def list_local_models(self) -> list[str]:
        """Returns model names reported by `ollama list`."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            lines = result.stdout.strip().splitlines()[1:]  # skip header
            models = []
            for line in lines:
                parts = line.split()
                if parts:
                    models.append(parts[0])
            return models
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    def _normalize_ollama_name(self, raw: str) -> str:
        """ollama list returns names like 'llama3.1:8b' — keep as-is."""
        return raw.strip()

    # ------------------------------------------------------------------ #
    # Routing
    # ------------------------------------------------------------------ #

    def route(
        self,
        prompt: str,
        available_models: Optional[list[str]] = None,
        prefer_fast: bool = False,
        min_vram_gb: Optional[float] = None,
        detect_hardware: bool = True,
    ) -> OllamaRoutingDecision:
        """
        Given a prompt, returns the best available local Ollama model.

        Args:
            prompt: The user's prompt.
            available_models: Override auto-discovered models. Useful for testing.
            prefer_fast: Bias toward smaller/faster models.
            min_vram_gb: Only consider models requiring <= this VRAM.
                         When None and detect_hardware=True, auto-detected from the machine.
            detect_hardware: Auto-detect RAM/VRAM to filter models that won't fit in memory.
        """
        if available_models is None:
            available_models = self.list_local_models()

        # Auto-detect hardware memory limit; explicit min_vram_gb takes precedence
        if min_vram_gb is None and detect_hardware:
            hw = self.hardware()
            min_vram_gb = hw.effective_model_memory_gb

        profile = self.classifier.classify(prompt)
        scored = self._score_models(profile, available_models, prefer_fast, min_vram_gb)

        if not scored:
            return OllamaRoutingDecision(
                model="llama3.1:8b",
                display_name="Llama 3.1 8B (fallback)",
                task_type=profile.task_type,
                complexity=profile.complexity,
                score=0.0,
                reason="No known models found locally; defaulting to llama3.1:8b",
                alternatives=[],
                available_models=available_models,
            )

        best = scored[0]
        alternatives = scored[1:4]

        reason = self._explain(best["model_id"], best["model_data"], profile, best["final_score"])

        return OllamaRoutingDecision(
            model=best["model_id"],
            display_name=best["model_data"].get("display_name", best["model_id"]),
            task_type=profile.task_type,
            complexity=profile.complexity,
            score=best["final_score"],
            reason=reason,
            alternatives=[
                {
                    "model": a["model_id"],
                    "display_name": a["model_data"].get("display_name", a["model_id"]),
                    "score": a["final_score"],
                }
                for a in alternatives
            ],
            available_models=available_models,
        )

    def _score_models(
        self,
        profile: TaskProfile,
        available_models: list[str],
        prefer_fast: bool,
        min_vram_gb: Optional[float],
    ) -> list[dict]:
        results = []

        for raw_model in available_models:
            model_id = self._normalize_ollama_name(raw_model)
            model_data = self.db.get_ollama_model(model_id)
            if model_data is None:
                model_data = self._infer_unknown_model(model_id)

            # VRAM filter
            if min_vram_gb is not None:
                req = model_data.get("min_vram_gb", 999)
                if req > min_vram_gb:
                    continue

            base_score = self.db.task_score(model_data, profile.task_type)
            strength_mult = self.db.strength_match(model_data, profile.task_type)
            final_score = base_score * strength_mult

            # Penalize underpowered models for complex tasks
            complexity_penalty = {
                "simple": 0,
                "moderate": 0,
                "hard": -5,
                "expert": -15,
            }.get(profile.complexity, 0)

            param_size = model_data.get("param_size", "7b")
            size_gb = self._param_to_gb(param_size)

            if profile.complexity in ("hard", "expert") and size_gb < 7:
                complexity_penalty -= 10
            if profile.complexity == "simple" and size_gb > 30 and prefer_fast:
                final_score -= 5  # prefer smaller for simple tasks when speed matters

            final_score += complexity_penalty

            # Long context bonus
            if profile.requires_long_context:
                ctx = model_data.get("context_window", 4096)
                if ctx >= 32000:
                    final_score += 3

            results.append(
                {
                    "model_id": model_id,
                    "raw_model": raw_model,
                    "model_data": model_data,
                    "base_score": base_score,
                    "final_score": round(final_score, 2),
                }
            )

        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results

    def _param_to_gb(self, param_str: str) -> float:
        """Converts '70b' → 70, '7b' → 7, '3.8b' → 3.8."""
        s = str(param_str).lower().replace("b", "").replace("m", "")
        try:
            v = float(s)
            if "m" in str(param_str).lower():
                v = v / 1000
            return v
        except ValueError:
            return 7.0

    def _infer_unknown_model(self, model_id: str) -> dict:
        """Best-effort inference for models not in the benchmark DB."""
        lower = model_id.lower()
        param_size = "7b"
        for size in ["70b", "34b", "32b", "27b", "14b", "13b", "8b", "7b", "3b", "1b"]:
            if size in lower:
                param_size = size
                break

        size_gb = self._param_to_gb(param_size)
        # Rough score by size: larger → more capable
        mmlu_est = min(86, 50 + size_gb * 0.5)
        humaneval_est = min(82, 45 + size_gb * 0.5)

        return {
            "display_name": model_id,
            "param_size": param_size,
            "benchmarks": {
                "mmlu": mmlu_est,
                "humaneval": humaneval_est,
                "math": mmlu_est - 10,
                "gpqa": mmlu_est - 30,
                "arc_challenge": mmlu_est + 5,
                "hellaswag": mmlu_est + 5,
                "lmsys_elo": 1100 + size_gb * 2,
                "reasoning_index": mmlu_est - 5,
                "swe_bench": humaneval_est - 30,
            },
            "strengths": ["general_tasks"],
            "weaknesses": [],
            "min_vram_gb": size_gb * 0.6,
        }

    def _explain(
        self, model_id: str, model_data: dict, profile: TaskProfile, score: float
    ) -> str:
        name = model_data.get("display_name", model_id)
        strengths = ", ".join(model_data.get("strengths", [])[:3])
        bench = profile.task_type
        bench_score = self.db.task_score(model_data, bench)
        return (
            f"Selected {name} (score {score:.1f}) for '{profile.task_type}' "
            f"task at '{profile.complexity}' complexity. "
            f"Benchmark on {bench}: {bench_score:.1f}/100. "
            f"Key strengths: {strengths}."
        )
