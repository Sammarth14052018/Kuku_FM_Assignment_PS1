import json
import logging
import os
import re
from typing import Any

from prompts import critic_prompt


def ask_json(system: str, user: str, retries: int = 1) -> dict | None:
    provider = os.getenv("PROVIDER", "openai").lower()
    temperature = 0 if system == critic_prompt() else 0.3
    client: Any
    try:
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(timeout=90, max_retries=1)
        elif provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(timeout=90, max_retries=1)
        else:
            raise ValueError("PROVIDER must be openai or anthropic")
        for _ in range(retries + 1):
            if provider == "openai":
                response = client.chat.completions.create(
                    model=os.getenv("MODEL", "gpt-4.1-mini"), temperature=temperature,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}])
                raw = response.choices[0].message.content or ""
            else:
                response = client.messages.create(
                    model=os.getenv("MODEL", "claude-haiku-4-5"), max_tokens=4000,
                    system=system, temperature=temperature,
                    messages=[{"role": "user", "content": user}])
                raw = "".join(block.text for block in response.content if block.type == "text")
            match = re.search(r"\{.*\}", raw, re.S)
            if match:
                try:
                    return json.loads(match[0])
                except json.JSONDecodeError:
                    pass
            logging.warning("Model returned invalid JSON")
    except Exception as exc:
        logging.error("%s request failed (%s)", provider, type(exc).__name__)
    return None
