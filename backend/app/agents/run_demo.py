"""Run the agent research loop from the command line.

Usage (from backend/, with .env containing OPENROUTER_API_KEY):

    python -m app.agents.run_demo AAPL
    python -m app.agents.run_demo BTC/USD "Is now a good entry?"

Without a key it prints the stub response, so it's always safe to run.
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.agents.graph import run_research
from app.agents.llm import is_configured


async def _main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    question = sys.argv[2] if len(sys.argv) > 2 else "Should we take a position, and why?"

    print(f"LLM configured: {is_configured()}")
    print(f"Researching {symbol}…\n")
    result = await run_research(symbol=symbol, question=question)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
