import pytest
from backend.app.models.debate import Debate, Question, DebateSide, Argument, ArgumentType
import uuid

def test_verdict_prompt_construction():
    """Verify that we can construct a transcript without throwing errors."""
    q = Question(text="Is AI dangerous?")
    d = Debate(id=uuid.uuid4(), question=q)
    
    side_for = DebateSide(id=uuid.uuid4(), debate_id=d.id, label="FOR", position="Yes")
    side_against = DebateSide(id=uuid.uuid4(), debate_id=d.id, label="AGAINST", position="No")
    
    arg1 = Argument(
        id=uuid.uuid4(), debate_id=d.id, round_id=uuid.uuid4(),
        participant_id=uuid.uuid4(), side_id=side_for.id,
        argument_type=ArgumentType.OPENING, content="AI is dangerous.", sequence=1
    )
    
    arguments = [arg1]
    sides = {side_for.id: side_for, side_against.id: side_against}
    
    transcript = ""
    for arg in arguments:
        side_label = sides.get(arg.side_id).label if arg.side_id in sides else "UNKNOWN"
        transcript += f"[{side_label}] {arg.argument_type.value}: {arg.content}\n\n"
        
    assert "[FOR] OPENING: AI is dangerous." in transcript
