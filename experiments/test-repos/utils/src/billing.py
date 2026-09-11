"""Billing module."""
from typing import List


def calculate_total(items: List[dict], tax_rate: float = 0.0) -> float:
    total = sum(item['price'] * item['quantity'] for item in items)
    if total < 0:
        raise ValueError("Total cannot be negative")
    return total * (1 + tax_rate)
