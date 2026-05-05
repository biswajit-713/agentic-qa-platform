"""
conftest.py

Pytest configuration. Adds project root to sys.path so src modules are importable.
Provides shared fixtures and helpers for all generated tests.
"""

import os
import sys
import json
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

SALEOR_GRAPHQL_URL = os.getenv("SALEOR_GRAPHQL_URL", "http://localhost:8000/graphql/")

_TOKEN_CREATE_MUTATION = """
mutation TokenCreate($email: String!, $password: String!) {
  tokenCreate(email: $email, password: $password) {
    token
    errors { field message }
  }
}
"""


def execute_graphql(query: str, variables: dict | None = None, headers: dict | None = None) -> dict:
    payload = {"query": query, "variables": variables or {}}
    try:
        response = httpx.post(SALEOR_GRAPHQL_URL, json=payload, headers=headers or {}, timeout=10.0)
    except httpx.RequestError as exc:
        pytest.fail(f"Network error while contacting Saleor: {exc}")
    if response.status_code != 200:
        pytest.fail(f"Unexpected status code {response.status_code}: {response.text}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        pytest.fail(f"Response is not valid JSON: {exc}")


@pytest.fixture(scope="module")
def channel_id(auth_headers):
    """Return the GraphQL ID of the default channel."""
    result = execute_graphql("{ channels { id slug } }", headers=auth_headers)
    channels = result.get("data", {}).get("channels", [])
    slug = os.getenv("SALEOR_DEFAULT_CHANNEL", "default-channel")
    for ch in channels:
        if ch["slug"] == slug:
            return ch["id"]
    if channels:
        return channels[0]["id"]
    pytest.skip(f"No channel with slug '{slug}' found in Saleor.")


@pytest.fixture(scope="module")
def auth_headers():
    """Fetch a fresh JWT token per test module using staff credentials from env vars.

    Token lifetime is ~5 min; module scope ensures a fresh token for each file.
    Reads SALEOR_STAFF_EMAIL + SALEOR_STAFF_PASSWORD from .env.
    Falls back to a static SALEOR_AUTH_TOKEN if set.
    """
    static_token = os.getenv("SALEOR_AUTH_TOKEN")
    if static_token:
        return {"Authorization": f"Bearer {static_token}"}

    email = os.getenv("SALEOR_STAFF_EMAIL")
    password = os.getenv("SALEOR_STAFF_PASSWORD")
    if not email or not password:
        pytest.skip(
            "Set SALEOR_STAFF_EMAIL + SALEOR_STAFF_PASSWORD (or SALEOR_AUTH_TOKEN) to run this test."
        )

    result = execute_graphql(_TOKEN_CREATE_MUTATION, {"email": email, "password": password})
    token_data = result.get("data", {}).get("tokenCreate", {})
    errors = token_data.get("errors", [])
    if errors:
        pytest.fail(f"tokenCreate failed: {errors}")
    token = token_data.get("token")
    if not token:
        pytest.fail("tokenCreate returned no token — check staff credentials.")
    return {"Authorization": f"Bearer {token}"}
