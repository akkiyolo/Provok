Plan our next turn. Do not write the turn itself.

ROUND: $round_name — we must deliver a $kind.
$round_guidance

CLAIM LEDGER (every claim made so far, with status)
$ledger_block

OUR RESEARCH FACTS
$facts_block

DEBATE SO FAR
$history_block

Decide:
- "targets": opponent claim seq numbers we should attack, weakest/most damaging first (max 3). Prefer claims that are unsupported, unaddressed, or central to their case.
- "defend": our own claim seq numbers that were attacked and must be defended (max 2).
- "new_points": 0-3 short new points to introduce, each tied to a fact id like "F2" where possible.
- "cross_exam_question_target": if we are asking a question, the single opponent claim seq to probe (their weakest unsupported or unaddressed claim); otherwise null.
- "search_query": a single web search query if a crucial fact is missing, otherwise null.
- "plan": one or two sentences describing the line of attack.

Reply with JSON only:
{"targets": [], "defend": [], "new_points": [], "cross_exam_question_target": null, "search_query": null, "plan": ""}
