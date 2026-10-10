import pytest
from backend.app.auth.security import create_access_token, verify_password, pwd_context
from datetime import timedelta

def test_password_hashing():
    password = "supersecretpassword"
    hashed = pwd_context.hash(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_create_access_token():
    subject = "user123"
    token = create_access_token(subject, expires_delta=timedelta(minutes=15))
    assert isinstance(token, str)
    assert len(token) > 20
