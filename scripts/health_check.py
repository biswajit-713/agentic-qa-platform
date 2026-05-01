"""
scripts/health_check.py

Verifies Day 1 setup: Saleor GraphQL is reachable and the Anthropic API key is valid.
Run from project root: python scripts/health_check.py

Exit codes:
  0 — all checks passed
  1 — one or more checks failed
"""

import logging
import sys
from pathlib import Path

# Allow importing src/ from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from src.config.settings import get_settings


def configure_logging(level: str) -> None:
    """Configure logging with timestamp and level formatting."""
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def check_saleor_graphql(graphql_url: str) -> bool:
    """Send a minimal introspection query to confirm Saleor GraphQL is up."""
    logger = logging.getLogger("health_check.saleor")
    query = {"query": "{ shop { name } }"}
    try:
        response = httpx.post(
            graphql_url,
            json=query,
            timeout=10.0,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        shop_name = data.get("data", {}).get("shop", {}).get("name")
        logger.info("Saleor GraphQL OK — shop name: %s", shop_name)
        return True
    except httpx.ConnectError:
        logger.error(
            "Cannot connect to Saleor at %s — is docker compose up?", graphql_url
        )
        return False
    except httpx.TimeoutException:
        logger.error("Saleor GraphQL timed out at %s", graphql_url)
        return False
    except Exception as exc:
        logger.error("Unexpected error checking Saleor: %s", exc)
        return False


def check_openrouter_api(base_url: str, api_key: str) -> bool:
    """Make a minimal OpenRouter API call to verify the key is valid and reachable."""
    logger = logging.getLogger("health_check.openrouter")
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-oss-120b:free",
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 10,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        logger.info("OpenRouter API OK — model: %s", data.get("model"))
        return True
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            logger.error("OpenRouter API key is invalid or expired")
        else:
            logger.error("OpenRouter API error: %s", exc)
        return False
    except httpx.ConnectError:
        logger.error("Cannot reach OpenRouter API at %s", base_url)
        return False
    except Exception as exc:
        logger.error("Unexpected error checking OpenRouter API: %s", exc)
        return False


def main() -> int:
    """Run all health checks and return exit code."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("health_check")

    logger.info("=== Agentic QA Platform — Day 1 Health Check ===")

    results: dict[str, bool] = {}

    logger.info("Check 1/2: Saleor GraphQL endpoint")
    results["saleor_graphql"] = check_saleor_graphql(str(settings.saleor_graphql_url))

    logger.info("Check 2/2: OpenRouter API connectivity")
    results["openrouter_api"] = check_openrouter_api(
        settings.openrouter_base_url, settings.openrouter_api_key
    )

    logger.info("--- Results ---")
    all_passed = True
    for check, passed in results.items():
        status = "PASS" if passed else "FAIL"
        logger.info("  %s: %s", check, status)
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("All checks passed. Day 1 setup is complete.")
        return 0
    else:
        logger.error("One or more checks failed. Review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
