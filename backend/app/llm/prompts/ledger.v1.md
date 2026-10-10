You maintain the claim ledger for a structured debate on: "$question".

EXISTING CLAIMS
$ledger_block

NEW TURN ($side_label, $round_name, $kind)
$turn_block

Extract the distinct substantive claims made in the new turn (max 6). Skip rhetoric, restatements and filler.
For each claim:
- "text": the claim in one neutral sentence (max 30 words), in the author's sense.
- "source_url": the URL it cites, if the turn explicitly cites one for this claim, else null.
- "responds_to": seq numbers of existing claims this one directly addresses (may be empty).
- "effect": how it treats those claims — "rebuts" (argues they are wrong), "concedes" (accepts them), "supports" (backs up a claim from the same side), or null.

$untrusted_notice

Reply with JSON only:
{"claims": [{"text": "...", "source_url": null, "responds_to": [], "effect": null}]}
