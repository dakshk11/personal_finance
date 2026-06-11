"""
Classifies prompts into task types and estimates complexity,
so the router can match to the best-benchmarked model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


TASK_TYPES = [
    "coding",
    "math",
    "reasoning",
    "science",
    "general_knowledge",
    "writing",
    "analysis",
    "conversation",
]

COMPLEXITY_LEVELS = ["simple", "moderate", "hard", "expert"]


@dataclass
class TaskProfile:
    task_type: str
    complexity: str
    requires_long_context: bool = False
    requires_tool_use: bool = False
    requires_structured_output: bool = False
    multilingual: bool = False
    language_hint: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    confidence: float = 1.0


# Keyword signatures per task type — ordered from most specific to general
_CODE_PATTERNS = [
    r"\b(function|def |class |import |#include|<\?php|var |const |let )\b",
    r"\b(debug|refactor|implement|fix the bug|write a (script|function|class|program)|code review)\b",
    r"\b(python|javascript|typescript|rust|golang|java|c\+\+|c#|ruby|kotlin|swift|bash|sql|html|css|react|fastapi|django|flask)\b",
    r"```[\w]*\n",
    r"\b(algorithm|data structure|recursion|loop|api endpoint|unit test|linting|dockerfile|kubernetes)\b",
]

_MATH_PATTERNS = [
    r"\b(solve|calculate|compute|evaluate|simplify|integrate|differentiate|prove|theorem|equation|matrix|vector|probability|statistics|derivative|integral)\b",
    r"[∫∑∏√±×÷≤≥≠∞αβγδεθλμπσφ]",
    r"\b\d+\s*[\+\-\*/\^]\s*\d+\b",
    r"\b(calculus|algebra|geometry|trigonometry|number theory|combinatorics|linear algebra|differential equation)\b",
]

_REASONING_PATTERNS = [
    r"\b(reason|infer|deduce|conclude|analyze|plan|strategy|step.by.step|chain of thought|think through)\b",
    r"\b(if .* then|given that|assuming|suppose|therefore|thus|hence|because)\b",
    r"\b(logic puzzle|brain teaser|riddle|constraint|optimization)\b",
]

_SCIENCE_PATTERNS = [
    r"\b(physics|chemistry|biology|neuroscience|genomics|quantum|relativity|thermodynamics|electromagnetism|biochemistry)\b",
    r"\b(molecule|protein|gene|cell|atom|electron|photon|entropy|hypothesis|experiment|research paper)\b",
    r"\b(phd|graduate level|academic|peer.reviewed|scientific|journal)\b",
]

_WRITING_PATTERNS = [
    r"\b(write|draft|compose|rewrite|proofread|edit|creative|story|essay|blog|poem|email|letter|report|summarize)\b",
    r"\b(tone|style|voice|narrative|introduction|conclusion|paragraph|thesis|argument)\b",
]

_ANALYSIS_PATTERNS = [
    r"\b(analyze|analyse|compare|contrast|evaluate|summarize|extract|explain|review|assess|critique)\b",
    r"\b(pros and cons|trade.off|advantages|disadvantages|breakdown|overview|insight)\b",
]

_COMPLEXITY_EASY = [
    r"\b(simple|quick|brief|short|what is|define|explain briefly|list|name)\b",
    r"^.{0,80}$",  # very short prompts
]

_COMPLEXITY_HARD = [
    r"\b(complex|advanced|in.depth|comprehensive|detailed|thoroughly|research.grade|dissertation|sophisticated)\b",
    r"\b(multiple|several|all|complete|entire|full|exhaustive|step.by.step)\b",
]

_COMPLEXITY_EXPERT = [
    r"\b(phd|graduate|research|novel|state.of.the.art|cutting.edge|frontier|breakthrough|rigorous)\b",
    r"\b(prove formally|mathematical proof|theorem|lemma|corollary)\b",
]

_LONG_CONTEXT = [
    r"\b(entire|whole|all of|full|document|paper|book|codebase|repository|history)\b",
    r"\b(long|extensive|thousands of|multiple files|batch)\b",
]

_TOOL_USE = [
    r"\b(search the web|browse|fetch|call an api|use a tool|execute|run a script)\b",
    r"\b(current news|today|latest|real.time|live data)\b",
]

_STRUCTURED_OUTPUT = [
    r"\b(json|xml|yaml|csv|table|markdown|structured|format|schema)\b",
    r"\b(output as|return as|respond with|provide as)\b",
]


def _match_score(text: str, patterns: list[str]) -> int:
    lower = text.lower()
    return sum(1 for p in patterns if re.search(p, lower, re.IGNORECASE))


class TaskClassifier:
    """Rule-based task classifier. Fast, zero-cost, no model calls needed."""

    def classify(self, prompt: str) -> TaskProfile:
        scores = {
            "coding": _match_score(prompt, _CODE_PATTERNS) * 2,
            "math": _match_score(prompt, _MATH_PATTERNS) * 2,
            "reasoning": _match_score(prompt, _REASONING_PATTERNS),
            "science": _match_score(prompt, _SCIENCE_PATTERNS) * 2,
            "writing": _match_score(prompt, _WRITING_PATTERNS) * 2,
            "analysis": _match_score(prompt, _ANALYSIS_PATTERNS),
            "conversation": 1,  # base fallback
            "general_knowledge": 0,
        }

        # Boost general knowledge if no strong signal
        if max(scores.values()) <= 1:
            scores["general_knowledge"] = 2
            scores["conversation"] = 1

        task_type = max(scores, key=lambda k: scores[k])
        confidence = min(1.0, scores[task_type] / 4.0)

        complexity = self._estimate_complexity(prompt, task_type)
        long_ctx = _match_score(prompt, _LONG_CONTEXT) > 0
        tool_use = _match_score(prompt, _TOOL_USE) > 0
        structured = _match_score(prompt, _STRUCTURED_OUTPUT) > 0
        multilingual = self._detect_non_english(prompt)

        keywords = [k for k, v in scores.items() if v > 0]

        return TaskProfile(
            task_type=task_type,
            complexity=complexity,
            requires_long_context=long_ctx,
            requires_tool_use=tool_use,
            requires_structured_output=structured,
            multilingual=multilingual,
            keywords=keywords,
            confidence=confidence,
        )

    def _estimate_complexity(self, prompt: str, task_type: str) -> str:
        expert_score = _match_score(prompt, _COMPLEXITY_EXPERT)
        hard_score = _match_score(prompt, _COMPLEXITY_HARD)
        easy_score = _match_score(prompt, _COMPLEXITY_EASY)

        # Science and math default harder
        if task_type in ("science", "math", "reasoning"):
            if expert_score > 0:
                return "expert"
            if hard_score > 0:
                return "hard"
            return "moderate"

        if expert_score > 0:
            return "expert"
        if hard_score > 0:
            return "hard"
        if easy_score > 0 and len(prompt.split()) < 20:
            return "simple"
        return "moderate"

    def _detect_non_english(self, prompt: str) -> bool:
        non_ascii = sum(1 for c in prompt if ord(c) > 127)
        return non_ascii / max(len(prompt), 1) > 0.15
