"""Shared prompt-context builders for the swarm, ledger and judge."""
from __future__ import annotations

from backend.app.engine.types import Persona, Round, TurnKind
from backend.app.models import Claim, Turn
from backend.app.moderation.injection import wrap

ROUND_NAMES = {Round.OPENING: "Opening", Round.REBUTTAL: "Rebuttal", Round.CROSS_EXAM: "Cross-examination",
               Round.CLOSING: "Closing"}

PERSONAS = {
    Persona.DATA_DRIVEN: "Data-driven. Anchor every point in evidence, numbers and studies. Calm, precise, clinical.",
    Persona.MORAL_FRAMING: "Moral framing. Argue from principles, rights, fairness and the human stakes. "
                           "Persuasive and humane, never preachy.",
    Persona.ECONOMIC: "Economic. Argue from incentives, costs, trade-offs and second-order effects.",
    Persona.CONTRARIAN: "Contrarian. Attack the framing and hidden assumptions of the motion itself. Sharp and "
                        "provocative, but rigorous.",
}

GUIDANCE = {
    (Round.OPENING, TurnKind.ARGUMENT): "Opening statement: define the key terms in your favour and set out your two "
                                        "or three strongest arguments. If the opponent has already opened, you may "
                                        "pre-empt their strongest point in one or two sentences.",
    (Round.REBUTTAL, TurnKind.ARGUMENT): "Rebuttal: attack the opponent's strongest claims by id, defend any of your "
                                         "own claims that were attacked, and add little new material.",
    (Round.CROSS_EXAM, TurnKind.QUESTION): "Cross-examination question: ask ONE sharp, answerable question that "
                                           "exposes the weakest unsupported or unaddressed claim in the opponent's "
                                           "case. One or two sentences. No speech, no preamble.",
    (Round.CROSS_EXAM, TurnKind.ANSWER): "Cross-examination answer: answer the question directly in your first "
                                         "sentence (yes/no if possible), then justify briefly. Stay consistent with "
                                         "your earlier claims. Do not ask a question back.",
    (Round.CLOSING, TurnKind.ARGUMENT): "Closing: crystallise the two or three decisive clashes, show why your side "
                                        "won each one, and weigh the impacts. No new arguments.",
}

QUESTION_WORD_CAP = 60


def side_label(position: str) -> str:
    return position.upper()


def ledger_block(claims: list[Claim], side_pos: dict, *, relative_to: str | None = None,
                 labels: dict[str, str] | None = None) -> str:
    if not claims:
        return "(no claims yet)"
    lines = []
    for c in claims:
        pos = side_pos.get(c.side_id, "?")
        if labels:
            who = f"Side {labels[pos]}"
        elif relative_to:
            who = "OURS" if pos == relative_to else "THEIRS"
        else:
            who = side_label(pos)
        src = f" [source: {c.source_url}]" if c.source_url else ""
        lines.append(f"C{c.seq} ({who}, {c.status}): {c.text}{src}")
    return "\n".join(lines)


def history_block(turns: list[Turn], side_pos: dict, *, labels: dict[str, str] | None = None) -> str:
    if not turns:
        return "(the debate has not started yet)"
    parts = []
    for t in turns:
        pos = side_pos.get(t.side_id, "?")
        label = labels[pos] if labels else side_label(pos)
        text = "[No response — turn forfeited]" if t.is_forfeit else t.content
        parts.append(f"--- {ROUND_NAMES[Round(t.round)]} · {t.kind} ---\n{wrap(text, side=label, kind=t.kind)}")
    return "\n\n".join(parts)


def facts_block(facts: list[dict]) -> str:
    if not facts:
        return "(no research available — argue from reasoning and do not cite)"
    return "\n".join(f"[{f['id']}] {f['fact']} (from: {f.get('title') or f['url']})" for f in facts)

