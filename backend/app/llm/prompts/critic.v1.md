You are the tough-minded coach reviewing a draft $kind before it goes live in the $round_name round. We argue $position_upper the motion "$question".

DRAFT
$draft

AVAILABLE FACTS
$facts_block

CLAIM LEDGER
$ledger_block

Check for:
1. Concessions of our core position (blocking).
2. Factual claims or statistics not backed by a listed fact and not framed as reasoning (blocking).
3. Citation markers [F#] that do not exist in the facts list (blocking).
4. Word count over $word_limit (blocking).
5. Logic gaps, strawmen, or ignoring the opponent's strongest live claim (blocking only if severe).
6. For a question: is it a single, sharp, answerable question? For an answer: does it stay consistent with our earlier claims?

Reply with JSON only:
{"blocking": true | false, "issues": ["short, specific, actionable issue", "..."]}
