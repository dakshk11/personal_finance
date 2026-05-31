from __future__ import annotations

import csv
from datetime import UTC, datetime
import io
import json
import re
from typing import Any
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PersonalCFOFile, PersonalCFOMessage, PersonalCFOProject, PersonalCFOUpload
from app.services.ai_advisor import generate_text, now_utc_naive, valid_ai_advisor_model


OPENING_MESSAGE = "Let's build your investor one-pager. Start by telling me where you live, what you do for income, and what the portfolio is for."
REFINEMENT_QUESTION = "Anything in here that doesn't sound like you?"

INVESTOR_STRATEGY_SYSTEM_PROMPT = """System Prompt - Investor Strategy Architect
Role
You are a McKinsey-caliber strategy advisor specialising in personal investment frameworks for high-performing operators - founders, executives, partners, and serious self-directed investors. You conduct rigorous discovery interviews and synthesise the output into a working investor one-pager: the kind of document an experienced operator drops into any AI tool, advisor relationship, or estate-planning conversation as instant context.

You are not a licensed financial advisor. You do not recommend specific assets, allocations, or tax strategies. You build the frame through which the user makes their own decisions.

Operating Principles
Probing over polite. Ask the question behind the question. If an answer is vague, name it and dig.
Constraints first, ambitions second. People over-state goals and under-state constraints. Spend disproportionate time on the latter.
Mindset > mechanics. A 60% allocation matters less than the rule for when to deviate from it. Push toward the underlying principle every time.
One sharp question at a time. Never barrage. Never ask three questions in a single turn. Wait for the answer, then go deeper.
Push back on contradictions. If they say "high conviction" and then list 18 positions, surface the gap immediately.
No fluff, no flattery. No "great question," no preamble, no recap. Direct, respectful, fast.
Their voice, not yours. The final document must read like the user wrote it. Use their phrasing, their edges, their specific language.

Interview Structure
Run through these seven phases in order. Do not move on until each is genuinely answered - not just acknowledged.
Phase 1 - Situation & Constraints
Operating base, residency, tax regime, expected duration of current setup
Income reality: sources, stability, gross vs net, predictability
Liquidity needs: does the portfolio fund life, or is it locked-up growth capital?
Realistic time budget for portfolio management (hours/week - be honest)
Family / partner dynamics and any non-negotiable constraints
Health, energy, attention - anything that limits active management
Phase 2 - Capital & Horizon
Rough capital base (bands are fine; exact figures unnecessary)
Time horizon split: tactical (months), core (years), generational (decade+)
Ability and willingness to add capital on a regular cadence
What the capital is for - generational wealth, F-you money, optionality, retirement, legacy?
Phase 3 - Philosophy & Mindset
Core investment beliefs in their own words - not borrowed from a book or podcast
Conviction style: concentrated vs diversified, and why
View on liquidity, leverage, and dry powder
How they have actually handled drawdowns historically - not what they think they would do
The biggest investment mistake they have made and what materially changed in their process afterward
Phase 4 - Behavioural Nuance
Known behavioural blind spots
What they over-weight, under-weight, or get emotional about
Triggers that have caused them to act badly in the past
Routines, rules, or guardrails already in place to manage themselves
Public-narrative exposure: do they discuss positions publicly? How does that distort their decisions?
Phase 5 - Preferences & Anti-Preferences
What categories, structures, and asset types they will buy
What they categorically will not buy, regardless of upside
Founders, sectors, vehicles, or pitches they avoid on principle
Sources they trust and sources they actively distrust
Phase 6 - Goals (Mindset Form, Not Numerical)
Compounding posture: when does the aggressive -> preservation transition begin, and what triggers it?
Drawdown tolerance - expressed as a state ("I can sleep through X% without changing my behaviour") rather than a number
The sleep test: at what point does a position size become unhealthy?
Decade-level orientation: what does "won" look like as a state of being, not a dollar figure?
Phase 7 - Stress Tests
Before synthesising, run two or three sharp hypotheticals. Pick the ones most likely to expose inconsistency:
"Your highest-conviction position drops 70% in a week. Walk me through what you do, hour by hour."
"A close friend offers you allocation in a deal that violates one of your stated rules. What happens?"
"It's 18 months from now and you've underperformed your benchmark by 30%. What's your honest reaction, and what's your next move?"
"You wake up to news that your single largest position is up 4x overnight on a takeover rumour. What do you do today?"
Use the answers to surface gaps between stated philosophy and likely behaviour. Reflect those gaps back. Adjust the final document accordingly.

Behavioural Rules During the Interview
Open with this exact line, nothing more:
"Let's build your investor one-pager. Start by telling me where you live, what you do for income, and what the portfolio is for." Then wait.
Never produce the final document until all seven phases are genuinely complete. If asked early, respond with: "We're not there yet. Next question:" and continue.
Refuse generic or borrowed answers. If the user says "buy and hold quality companies" or "be greedy when others are fearful," push back: "That's a quote, not a belief. Say it again in your own words, anchored to a specific decision you've actually made."
Name contradictions directly. "Earlier you said X. Now you're saying Y. Which is true?"
Resist scope creep. If the user wants tactical advice, redirect: "That's not what this document does. Back to the framework."
One round of refinement after the document is produced. Then stop. Do not oversell, do not summarise, do not add commentary. The document is the deliverable.

Output Specification
When - and only when - all seven phases are complete, produce a markdown file with exactly this structure. Match the section order and headings precisely.

# Investor One-Pager - [Name]

**Last updated:** [Date]
**Operating base:** [Location, residency status, tax regime]

---

## North Star
[2-4 sentences. The compounding-to-preservation arc, the asymmetric posture, the floor that keeps them sleeping at night. In their voice, not generic advisor-speak.]

---

## Core Philosophy
[5-7 bullets. Beliefs in their own words. Each bullet must be defensible and specific - not a platitude. Bold the principle, then expand in one short sentence.]

---

## Time Horizon
[Short paragraph on the tactical / core / generational split and the rules that keep the books psychologically separate.]

---

## Mindset Rules
[Numbered list of 6-9 rules. Each is a behavioural commitment, not a strategy. Imperative voice. Short, memorable, executable under stress.]

---

## Personal Nuances
[Bulleted list. Tax, income & liquidity, time budget, family constraints, behavioural blind spots, routines, conference / public-exposure rules. The constraints that make this strategy theirs and not transferable to anyone else.]

---

## Anti-Portfolio
[Bulleted list of categorical "won't buy" criteria, regardless of upside. Sharp, specific, and slightly opinionated.]

---

*This document is reviewed every [cadence]. Material changes require a [cooldown period] before execution.*

Final Instructions
The deliverable is the markdown file. Nothing else.
After producing it, ask exactly once: "Anything in here that doesn't sound like you?" - then incorporate edits and stop.
Do not append disclaimers, summaries, or "I hope this helps." The document speaks for itself."""

PHASES: tuple[dict[str, str], ...] = (
    {"id": "1", "name": "Situation & Constraints"},
    {"id": "2", "name": "Capital & Horizon"},
    {"id": "3", "name": "Philosophy & Mindset"},
    {"id": "4", "name": "Behavioural Nuance"},
    {"id": "5", "name": "Preferences & Anti-Preferences"},
    {"id": "6", "name": "Goals"},
    {"id": "7", "name": "Stress Tests"},
)
PHASE_TARGETS = {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "7": 2}
GENERIC_ANSWERS = (
    "buy and hold quality companies",
    "be greedy when others are fearful",
    "time in the market beats timing the market",
    "diversification is the only free lunch",
)
GENERIC_PUSHBACK = "That's a quote, not a belief. Say it again in your own words, anchored to a specific decision you've actually made."
FILE_INVESTOR_ONE_PAGER = "investor-one-pager.md"
FILE_INSTRUCTIONS = "instructions.md"
FILE_MEMORY = "memory.md"
FILE_SYSTEM_PROMPT = "investor-strategy-system-prompt.md"


class PersonalCFOStateError(RuntimeError):
    pass


def create_project(db: Session, user_id: int, name: str) -> PersonalCFOProject:
    project_name = name.strip() or "Investment Folder"
    project = PersonalCFOProject(user_id=user_id, name=project_name, phase_progress_json="{}")
    db.add(project)
    db.flush()
    db.add(PersonalCFOMessage(project_id=project.id, role="assistant", content=OPENING_MESSAGE, phase=1))
    for path, (kind, content) in _default_files(project_name).items():
        db.add(PersonalCFOFile(project_id=project.id, path=path, kind=kind, content=content))
    db.commit()
    db.refresh(project)
    return project


def submit_interview_message(db: Session, project: PersonalCFOProject, api_key: str | None, model: str, content: str, ollama_base_url: str | None = None) -> PersonalCFOProject:
    if not valid_ai_advisor_model(model):
        raise ValueError("Unsupported OpenAI model.")
    if project.one_pager_generated:
        raise PersonalCFOStateError("The interview is already complete. Use the refinement action for the one allowed edit round.")

    phase = _current_phase(project)
    cleaned = content.strip()
    db.add(PersonalCFOMessage(project_id=project.id, role="user", content=cleaned, phase=phase))

    if _is_generic_answer(cleaned):
        db.add(PersonalCFOMessage(project_id=project.id, role="assistant", content=GENERIC_PUSHBACK, phase=phase))
        db.commit()
        db.refresh(project)
        return project

    _advance_phase(project)
    db.flush()
    if phase_complete(project):
        assistant_text = "All seven phases are complete. Generate the one-pager when you're ready."
    else:
        response_text, _payload = generate_text(
            model,
            _build_interview_prompt(db, project),
            api_key=api_key,
            ollama_base_url=ollama_base_url,
            instructions=INVESTOR_STRATEGY_SYSTEM_PROMPT,
        )
        assistant_text = _one_question_only(response_text)
    db.add(PersonalCFOMessage(project_id=project.id, role="assistant", content=assistant_text, phase=_current_phase(project)))
    _touch_project(project)
    db.commit()
    db.refresh(project)
    return project


def generate_one_pager(db: Session, project: PersonalCFOProject, api_key: str | None, model: str, ollama_base_url: str | None = None) -> PersonalCFOProject:
    if not valid_ai_advisor_model(model):
        raise ValueError("Unsupported OpenAI model.")
    if not phase_complete(project):
        raise PersonalCFOStateError("We're not there yet. Complete all seven interview phases before generating the one-pager.")
    if project.one_pager_generated:
        raise PersonalCFOStateError("The investor one-pager has already been generated. Use the single refinement round instead.")

    response_text, _payload = generate_text(
        model,
        _build_one_pager_prompt(db, project),
        api_key=api_key,
        ollama_base_url=ollama_base_url,
        instructions=INVESTOR_STRATEGY_SYSTEM_PROMPT,
    )
    one_pager = _ensure_one_pager_structure(response_text, project.name)
    _ensure_file(db, project, FILE_INVESTOR_ONE_PAGER).content = one_pager
    _ensure_file(db, project, FILE_SYSTEM_PROMPT).content = INVESTOR_STRATEGY_SYSTEM_PROMPT
    _ensure_file(db, project, FILE_INSTRUCTIONS).content = _instructions_markdown(project.name)
    _append_memory_event(db, project, "Investor one-pager generated from completed seven-phase interview.")
    project.one_pager_generated = True
    project.status = "one_pager_ready"
    _touch_project(project)
    db.add(PersonalCFOMessage(project_id=project.id, role="assistant", content=REFINEMENT_QUESTION, phase=None))
    db.commit()
    db.refresh(project)
    return project


def refine_one_pager(db: Session, project: PersonalCFOProject, api_key: str | None, model: str, feedback: str, ollama_base_url: str | None = None) -> PersonalCFOProject:
    if not valid_ai_advisor_model(model):
        raise ValueError("Unsupported OpenAI model.")
    if not project.one_pager_generated:
        raise PersonalCFOStateError("Generate the investor one-pager before refining it.")
    if project.refinement_used:
        raise PersonalCFOStateError("The one allowed refinement round has already been used.")

    existing = _ensure_file(db, project, FILE_INVESTOR_ONE_PAGER).content
    prompt = (
        "Incorporate the user's refinement into the investor one-pager below. "
        "Return only the full updated markdown file using the exact required section order and headings.\n\n"
        f"User refinement:\n{feedback.strip()}\n\nExisting one-pager:\n{existing}"
    )
    response_text, _payload = generate_text(model, prompt, api_key=api_key, ollama_base_url=ollama_base_url, instructions=INVESTOR_STRATEGY_SYSTEM_PROMPT)
    one_pager = _ensure_one_pager_structure(response_text, project.name)
    _ensure_file(db, project, FILE_INVESTOR_ONE_PAGER).content = one_pager
    _append_memory_event(db, project, "Investor one-pager refined once from user feedback.")
    project.refinement_used = True
    project.status = "refined"
    _touch_project(project)
    db.add(PersonalCFOMessage(project_id=project.id, role="user", content=feedback.strip(), phase=None))
    db.commit()
    db.refresh(project)
    return project


def update_file(db: Session, project: PersonalCFOProject, file_id: int, content: str) -> PersonalCFOFile:
    file_row = db.get(PersonalCFOFile, file_id)
    if not file_row or file_row.project_id != project.id:
        raise PersonalCFOStateError("Personal CFO file not found.")
    file_row.content = content
    file_row.updated_at = now_utc_naive()
    _touch_project(project)
    db.commit()
    db.refresh(file_row)
    return file_row


def create_upload(db: Session, project: PersonalCFOProject, file_name: str, content: str) -> PersonalCFOUpload:
    safe_name = _safe_file_name(file_name)
    file_type = _upload_file_type(safe_name)
    if file_type not in {"csv", "markdown"}:
        raise ValueError("Only markdown and CSV uploads are supported.")
    rows = _parse_csv(content) if file_type == "csv" else []
    upload = PersonalCFOUpload(
        project_id=project.id,
        file_name=safe_name,
        file_type=file_type,
        content=content,
        parsed_json=json.dumps(rows, separators=(",", ":"), sort_keys=True),
    )
    db.add(upload)
    _append_memory_event(db, project, f"Uploaded {safe_name} into Financials/.")
    _touch_project(project)
    db.commit()
    db.refresh(upload)
    return upload


def dashboard_summary(project: PersonalCFOProject) -> dict[str, Any]:
    csv_rows = _all_csv_rows(project.uploads)
    cash_trend = _cash_trend(csv_rows)
    exposures = _exposures(csv_rows)
    memory = _file_content(project, FILE_MEMORY)
    one_pager = _file_content(project, FILE_INVESTOR_ONE_PAGER)
    return {
        "project_id": project.id,
        "files_count": len(project.files),
        "uploads_count": len(project.uploads),
        "message_count": len(project.messages),
        "cash_trend": cash_trend,
        "pnl_summary": _pnl_summary(csv_rows),
        "exposures": exposures,
        "memory_timeline": _memory_timeline(memory),
        "open_flags": _open_flags(one_pager),
    }


def export_project_zip(db: Session, project: PersonalCFOProject) -> bytes:
    project.last_exported_at = now_utc_naive()
    _append_memory_event(db, project, "Investment Folder ZIP exported.")
    _touch_project(project)
    db.flush()

    buffer = io.BytesIO()
    file_map = {file_row.path: file_row.content for file_row in project.files}
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in (FILE_INVESTOR_ONE_PAGER, FILE_INSTRUCTIONS, FILE_MEMORY, FILE_SYSTEM_PROMPT):
            archive.writestr(path, file_map.get(path, ""))
        archive.writestr("Financials/", "")
        for upload in project.uploads:
            archive.writestr(f"Financials/{_safe_file_name(upload.file_name)}", upload.content)
    db.commit()
    return buffer.getvalue()


def load_phase_progress(project: PersonalCFOProject) -> dict[str, int]:
    try:
        raw = json.loads(project.phase_progress_json or "{}")
    except json.JSONDecodeError:
        return {}
    return {str(key): int(value) for key, value in raw.items() if str(value).isdigit() or isinstance(value, int)}


def phase_complete(project: PersonalCFOProject) -> bool:
    return project.current_phase > len(PHASES)


def upload_row_count(upload: PersonalCFOUpload) -> int:
    try:
        rows = json.loads(upload.parsed_json or "[]")
    except json.JSONDecodeError:
        return 0
    return len(rows) if isinstance(rows, list) else 0


def _default_files(project_name: str) -> dict[str, tuple[str, str]]:
    return {
        FILE_INVESTOR_ONE_PAGER: ("markdown", ""),
        FILE_INSTRUCTIONS: ("markdown", _instructions_markdown(project_name)),
        FILE_MEMORY: ("markdown", _memory_markdown("Personal CFO project created.")),
        FILE_SYSTEM_PROMPT: ("markdown", INVESTOR_STRATEGY_SYSTEM_PROMPT),
    }


def _instructions_markdown(project_name: str) -> str:
    owner = project_name.replace("Investment Folder", "").strip() or "Personal CFO"
    return f"""# Project Instructions - {owner} Investor OS

You are {owner}'s investment strategist. Operate as a McKinsey-caliber advisor: probing, direct, no fluff, no flattery. You are not a licensed financial advisor; your job is to frame decisions, never to make them.

## Files in this project

- `investor-one-pager.md` - Core mindset and strategy. Authoritative. Stable.
- `memory.md` - Personal info, evolving context, and timestamped change log. Always current.
- `investor-strategy-system-prompt.md` - Source interview prompt used to rebuild the one-pager from scratch.
- `Financials/` - Live cash position and financial context. Reference only.
- `Financials/pnl-summary.md` - Rolling 6-month P&L when supplied.
- `Financials/bank-statement-[month]-[year].md` - Monthly source statements when supplied.

## Rules

1. Read `investor-one-pager.md` and `memory.md` before every response. Treat both as canonical.
2. Whenever new information emerges in conversation, update `memory.md` immediately. This covers life changes, jurisdiction or tax shifts, income changes, new positions, new constraints, behavioural patterns observed, and evolving views. Append, never overwrite. Date every entry.
3. Before any advice that touches deployment, sizing, or cash management, read `Financials/pnl-summary.md`. Bank statements are the source of truth if numbers are queried.
4. Never silently overwrite the one-pager. If new information contradicts it, surface the conflict and ask whether `investor-one-pager.md` should be revised.
5. Run every proposed action against the stated rules. If something violates a rule in the one-pager, name the rule before anything else.
6. Match the user's voice in any document edits. Their phrasing, their edges, their language, not generic advisor-speak.
7. No preamble, no recap, no flattery. Direct response, every time.

## Default posture

- Briefly note which file(s) informed the response.
- Probe before advising. One sharp question beats ten unsolicited recommendations.
- Surface contradictions immediately; never let stated philosophy and stated action quietly diverge.
- End with the next question or the next action. Never a summary.
"""


def _memory_markdown(event: str) -> str:
    return f"""# Change Log

**{_today_label()}**
- {event}

*New entries go above this line, dated, in reverse chronological order.*
"""


def _append_memory_event(db: Session, project: PersonalCFOProject, event: str) -> None:
    memory = _ensure_file(db, project, FILE_MEMORY)
    entry = f"\n**{_today_label()}**\n- {event}\n"
    marker = "\n*New entries go above this line"
    content = memory.content or "# Change Log\n\n*New entries go above this line, dated, in reverse chronological order.*\n"
    if marker in content:
        memory.content = content.replace(marker, f"{entry}{marker}", 1)
    else:
        memory.content = f"{content.rstrip()}\n{entry}\n"
    memory.updated_at = now_utc_naive()


def _ensure_file(db: Session, project: PersonalCFOProject, path: str) -> PersonalCFOFile:
    for file_row in project.files:
        if file_row.path == path:
            return file_row
    file_row = db.scalar(select(PersonalCFOFile).where(PersonalCFOFile.project_id == project.id, PersonalCFOFile.path == path))
    if file_row:
        return file_row
    kind, content = _default_files(project.name).get(path, ("markdown", ""))
    file_row = PersonalCFOFile(project_id=project.id, path=path, kind=kind, content=content)
    db.add(file_row)
    db.flush()
    return file_row


def _current_phase(project: PersonalCFOProject) -> int:
    return min(max(project.current_phase, 1), len(PHASES))


def _advance_phase(project: PersonalCFOProject) -> None:
    phase_id = str(_current_phase(project))
    progress = load_phase_progress(project)
    progress[phase_id] = progress.get(phase_id, 0) + 1
    if progress[phase_id] >= PHASE_TARGETS[phase_id]:
        if project.current_phase < len(PHASES):
            project.current_phase += 1
            project.status = "interview"
        else:
            project.current_phase = len(PHASES) + 1
            project.status = "ready_for_one_pager"
    project.phase_progress_json = json.dumps(progress, separators=(",", ":"), sort_keys=True)


def _is_generic_answer(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    if len(normalized) < 8:
        return True
    return any(quote in normalized for quote in GENERIC_ANSWERS)


def _build_interview_prompt(db: Session, project: PersonalCFOProject) -> str:
    phase = PHASES[_current_phase(project) - 1]
    return (
        f"Project name: {project.name}\n"
        f"Current phase: Phase {phase['id']} - {phase['name']}\n"
        f"Phase progress: {project.phase_progress_json or '{}'}\n\n"
        "Continue the interview using the system rules. Ask exactly one sharp question. "
        "Do not produce the investor one-pager. If the latest answer is vague, generic, or contradictory, push back directly.\n\n"
        f"Transcript:\n{_transcript(db, project)}"
    )


def _build_one_pager_prompt(db: Session, project: PersonalCFOProject) -> str:
    return (
        "All seven phases are complete. Produce the final markdown file now using exactly the Output Specification in the system prompt. "
        "Return the markdown file only.\n\n"
        f"Project name: {project.name}\n"
        f"Transcript:\n{_transcript(db, project)}"
    )


def _transcript(db: Session, project: PersonalCFOProject) -> str:
    messages = db.scalars(
        select(PersonalCFOMessage)
        .where(PersonalCFOMessage.project_id == project.id)
        .order_by(PersonalCFOMessage.id.asc())
    ).all()
    return "\n".join(f"{message.role.title()}: {message.content}" for message in messages)


def _one_question_only(value: str) -> str:
    cleaned = value.strip()
    question_index = cleaned.find("?")
    if question_index >= 0:
        return cleaned[: question_index + 1].strip()
    first_line = cleaned.splitlines()[0].strip() if cleaned else ""
    return first_line or "What is the constraint here that would actually change how you invest?"


def _ensure_one_pager_structure(value: str, project_name: str) -> str:
    cleaned = value.strip()
    required = (
        "# Investor One-Pager",
        "## North Star",
        "## Core Philosophy",
        "## Time Horizon",
        "## Mindset Rules",
        "## Personal Nuances",
        "## Anti-Portfolio",
    )
    if all(section in cleaned for section in required):
        return cleaned
    owner = project_name.replace("Investment Folder", "").strip() or "Personal CFO"
    return f"""# Investor One-Pager - {owner}

**Last updated:** {_today_label()}
**Operating base:** Not specified

---

## North Star
{cleaned or "The interview is complete, but the generated response did not include usable one-pager language."}

---

## Core Philosophy
- **Use explicit rules.** Decisions need to be judged against stated constraints, not market noise.
- **Separate time horizons.** Tactical, core, and decade-plus capital should not share the same emotional ledger.
- **Protect attention.** The framework must fit the time and energy actually available.
- **Name contradictions.** When stated beliefs and likely behaviour diverge, the rule needs to be rewritten.
- **Preserve optionality.** Liquidity and sleep matter because they determine whether the plan survives stress.

---

## Time Horizon
Tactical, core, and generational capital are kept psychologically separate until the user defines sharper boundaries.

---

## Mindset Rules
1. State the rule before the action.
2. Do not turn stress into a new strategy.
3. Keep position size inside the sleep test.
4. Treat liquidity as a constraint, not an afterthought.
5. Revisit the one-pager before material changes.
6. Cool down before overriding a rule.

---

## Personal Nuances
- Operating base, tax regime, income cadence, liquidity needs, family constraints, and attention budget need periodic review.
- Behavioural blind spots and public-narrative distortions should be logged in `memory.md` as they appear.

---

## Anti-Portfolio
- Won't buy anything that violates the stated rules regardless of upside.
- Won't let friend allocation, hype, or public narrative override the framework.

---

*This document is reviewed every quarter. Material changes require a 48-hour cooldown period before execution.*
"""


def _parse_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return []
    return [{str(key).strip(): str(value).strip() for key, value in row.items() if key is not None} for row in reader]


def _all_csv_rows(uploads: list[PersonalCFOUpload]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for upload in uploads:
        if upload.file_type != "csv":
            continue
        try:
            parsed = json.loads(upload.parsed_json or "[]")
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            rows.extend(row for row in parsed if isinstance(row, dict))
    return rows


def _cash_trend(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        date_value = _field(row, ("date", "as_of_date", "month", "period"))
        cash = _number(_field(row, ("cash", "cash_balance", "balance", "bank_balance")))
        if date_value and cash is not None:
            points.append({"date": str(date_value), "value": cash})
    return sorted(points, key=lambda point: str(point["date"]))[-24:]


def _pnl_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_pnl = 0.0
    total_contributions = 0.0
    pnl_rows = 0
    for row in rows:
        pnl = _number(_field(row, ("pnl", "p&l", "profit_loss", "profit/loss", "gain_loss")))
        contribution = _number(_field(row, ("contribution", "deposit", "transfer_in", "amount")))
        if pnl is not None:
            total_pnl += pnl
            pnl_rows += 1
        if contribution is not None:
            total_contributions += contribution
    return {
        "total_pnl": round(total_pnl, 2),
        "total_contributions": round(total_contributions, 2),
        "pnl_rows": pnl_rows,
        "source_rows": len(rows),
    }


def _exposures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, float] = {}
    for row in rows:
        label = _field(row, ("symbol", "ticker", "category", "asset_class", "asset", "name"))
        value = _number(_field(row, ("market_value", "value", "amount", "position_value", "balance")))
        if label and value is not None:
            buckets[str(label).upper()] = buckets.get(str(label).upper(), 0.0) + value
    total = sum(abs(value) for value in buckets.values())
    exposures = [
        {"label": label, "value": round(value, 2), "weight": round(abs(value) / total, 4) if total else 0}
        for label, value in sorted(buckets.items(), key=lambda item: abs(item[1]), reverse=True)
    ]
    return exposures[:12]


def _memory_timeline(content: str) -> list[str]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    timeline: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith("**") and line.endswith("**"):
            next_line = lines[index + 1] if index + 1 < len(lines) and lines[index + 1].startswith("-") else ""
            timeline.append(f"{line.strip('*')} {next_line.lstrip('- ').strip()}".strip())
    return timeline[:10]


def _open_flags(content: str) -> list[str]:
    flags: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip("-*# 1234567890.").strip()
        lowered = line.lower()
        if not line:
            continue
        if any(token in lowered for token in ("contradiction", "earlier you said", "won't buy", "do not", "never ", "requires")):
            flags.append(line)
    return flags[:10]


def _file_content(project: PersonalCFOProject, path: str) -> str:
    for file_row in project.files:
        if file_row.path == path:
            return file_row.content or ""
    return ""


def _field(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    normalized = {str(key).lower().strip().replace(" ", "_"): value for key, value in row.items()}
    for candidate in candidates:
        key = candidate.lower().strip().replace(" ", "_")
        if key in normalized and str(normalized[key]).strip():
            return normalized[key]
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _upload_file_type(file_name: str) -> str:
    lower = file_name.lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".md") or lower.endswith(".markdown"):
        return "markdown"
    return ""


def _safe_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "", file_name).strip().replace("/", "-")
    return cleaned or "financial-upload.md"


def _touch_project(project: PersonalCFOProject) -> None:
    project.updated_at = now_utc_naive()


def _today_label() -> str:
    return datetime.now(UTC).strftime("%d %b %Y")
