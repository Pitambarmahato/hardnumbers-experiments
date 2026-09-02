"""Tests for users module."""
from src.users import APIClient, fetch_user


def test_fetch_user_returns_dict():
    client = APIClient()
    result = fetch_user(client, 1)
    assert isinstance(result, dict)


def test_fetch_user_has_id():
    client = APIClient()
    result = fetch_user(client, 42)
    assert result['id'] == 42
