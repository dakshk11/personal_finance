"""
Loads and queries model benchmark data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


_DEFAULT_DB = Path(__file__).parent / "benchmarks" / "model_benchmarks.json"


class BenchmarkDB:
    def __init__(self, db_path: Optional[str] = None):
        path = Path(db_path) if db_path else _DEFAULT_DB
        with open(path) as f:
            self._data = json.load(f)
        self._frontier = self._data["frontier_models"]
        self._ollama = self._data["ollama_models"]
        self._task_map = self._data["task_benchmark_mapping"]

    # ------------------------------------------------------------------ #
    # Frontier model queries
    # ------------------------------------------------------------------ #

    def get_frontier_model(self, model_id: str) -> Optional[dict]:
        return self._frontier.get(model_id)

    def all_frontier_models(self) -> dict[str, dict]:
        return self._frontier

    def frontier_models_by_provider(self, provider: str) -> dict[str, dict]:
        return {k: v for k, v in self._frontier.items() if v["provider"] == provider}

    # ------------------------------------------------------------------ #
    # Ollama model queries
    # ------------------------------------------------------------------ #

    def get_ollama_model(self, model_id: str) -> Optional[dict]:
        # Exact match first, then fuzzy prefix match
        if model_id in self._ollama:
            return self._ollama[model_id]
        for k, v in self._ollama.items():
            if k.startswith(model_id) or model_id.startswith(k.split(":")[0]):
                return v
        return None

    def all_ollama_models(self) -> dict[str, dict]:
        return self._ollama

    def known_ollama_model_ids(self) -> list[str]:
        return list(self._ollama.keys())

    # ------------------------------------------------------------------ #
    # Scoring helpers
    # ------------------------------------------------------------------ #

    def task_score(self, model_data: dict, task_type: str) -> float:
        """Returns a 0-100 score for a model on a given task type."""
        mapping = self._task_map.get(task_type, {})
        primary = mapping.get("primary", "mmlu")
        secondary = mapping.get("secondary", [])

        benchmarks = model_data.get("benchmarks", {})

        primary_val = benchmarks.get(primary, 0)
        sec_vals = [benchmarks.get(s, 0) for s in secondary if s in benchmarks]
        sec_avg = sum(sec_vals) / len(sec_vals) if sec_vals else primary_val

        # Weighted: 70% primary, 30% secondary avg
        score = 0.7 * primary_val + 0.3 * sec_avg

        # Normalize lmsys_elo to 0-100 range (1000-1400 → 0-100)
        if primary == "lmsys_elo":
            score = 0.7 * ((benchmarks.get("lmsys_elo", 1000) - 1000) / 4.0)
            score += 0.3 * sec_avg

        return round(score, 2)

    def strength_match(self, model_data: dict, task_type: str) -> float:
        """Bonus multiplier if task_type is in model's strengths list."""
        strengths = model_data.get("strengths", [])
        task_keywords = {
            "coding": ["code", "coding", "code_specialized", "swe", "fill_in_middle", "code_completion"],
            "math": ["math", "hard_math"],
            "reasoning": ["deep_reasoning", "reasoning", "chain_of_thought", "hard_reasoning"],
            "science": ["science", "research_grade_analysis", "scientific"],
            "writing": ["writing", "creative"],
            "analysis": ["analysis", "long_context"],
            "conversation": ["conversational", "chat"],
            "general_knowledge": ["general_tasks", "balanced"],
        }
        hits = task_keywords.get(task_type, [])
        for h in hits:
            for s in strengths:
                if h in s or s in h:
                    return 1.15
        return 1.0
