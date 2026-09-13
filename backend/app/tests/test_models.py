import pytest
from backend.app.models.user import User
from backend.app.models.debate import Debate, Question
import uuid
from datetime import datetime, timezone

def test_user_creation():
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        username="testuser",
        password_hash="hashed_password",
        is_active=True
    )
    assert user.email == "test@example.com"
    assert user.username == "testuser"
    assert user.is_active is True

def test_debate_creation():
    question = Question(
        id=uuid.uuid4(),
        text="Is space exploration worth the cost?",
        author_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc)
    )
    
    debate = Debate(
        id=uuid.uuid4(),
        question_id=question.id,
        debate_type="HUMAN_VS_AI",
        mode="LIVE",
        status="DRAFT"
    )
    
    assert debate.debate_type == "HUMAN_VS_AI"
    assert debate.status == "DRAFT"
    assert debate.question_id == question.id


def test_agent_vs_agent_debate_model():
    """Test AI_VS_AI debate creation and schema validation."""
    from backend.app.models.debate import DebateType, SideLabel
    from backend.app.schemas.debate import DebateCreate

    schema = DebateCreate(
        title="Will AGI replace software engineers by 2030?",
        opponent_type="AI_VS_AI",
        initial_position=SideLabel.FOR,
        is_public=True
    )
    assert schema.opponent_type == "AI_VS_AI"
    assert schema.title == "Will AGI replace software engineers by 2030?"

    debate = Debate(
        id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        debate_type=DebateType.AI_VS_AI,
        mode="LIVE",
        status="LIVE"
    )
    assert debate.debate_type == DebateType.AI_VS_AI

