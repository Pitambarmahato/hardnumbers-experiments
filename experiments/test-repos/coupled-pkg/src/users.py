"""Users module."""
from typing import Optional


class APIClient:
    def fetch(self, endpoint: str) -> dict:
        return {'id': 1, 'name': 'Alice'}

    def get_user(self, user_id: int) -> dict:
        return {'id': user_id, 'name': 'Alice'}


def fetch_user(client: APIClient, user_id: int) -> Optional[dict]:
    """Fetch a user by ID. Returns the user dict or None."""
    response = client.fetch(endpoint=f'/users/{user_id}')
    return response or None
