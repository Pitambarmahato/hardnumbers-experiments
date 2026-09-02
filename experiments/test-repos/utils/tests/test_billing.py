"""Tests for billing module."""
from src.billing import calculate_total


def test_calculate_total_empty():
    assert calculate_total([]) == 0


def test_calculate_total_basic():
    items = [{'price': 10.0, 'quantity': 2}, {'price': 5.0, 'quantity': 3}]
    assert calculate_total(items) == 35.0
