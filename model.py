import logging
import os
import json
from typing import Dict, List
from uuid import UUID
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def map_product_controls_with_llm(product_a: Dict, product_b: Dict) -> List[Dict]:
    """
    Map all controls of product A to product B in **one LLM call**.

    product_a, product_b:
        {
            "id": <UUID>,
            "controls": [
                {"id": <UUID>, "text": "...", "metadata": {...}},
                ...
            ]
        }

    Returns a list of mappings:
        [
            {"source_id": <control_a_uuid>, "target_id": <control_b_uuid>, "confidence": 0.92},
            ...
        ]
    """

    # Prepare text for LLM prompt
    controls_a_text = "\n".join([f"- {c['id']}: {c['text']}" for c in product_a["controls"]])
    controls_b_text = "\n".join([f"- {c['id']}: {c['text']}" for c in product_b["controls"]])

    prompt = f"""
You are a compliance control mapping assistant.
Your task is to map controls from Product A to equivalent controls in Product B.

Rules:
- Only map controls that are truly equivalent or highly similar in intent.
- If a control has no good match, do not include it.
- Provide a confidence score between 0 and 1.
- Only output valid JSON as a list.

Product A Controls:
{controls_a_text}

Product B Controls:
{controls_b_text}

Output example:
[
  {{"source_id": "<UUID of control A>", "target_id": "<UUID of control B>", "confidence": 0.92}},
  ...
]
    """

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert compliance control mapper."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0
        )

        raw_output = response.choices[0].message.content.strip()
        logger.debug(f"LLM raw output: {raw_output}")

        # Parse JSON output
        try:
            mappings = json.loads(raw_output)
            db_mappings = []

            for m in mappings:
                if "source_id" in m and "target_id" in m:
                    db_mappings.append({
                        "source_id": m["source_id"],
                        "target_id": m["target_id"],
                        "confidence": float(m.get("confidence", 0.0)),
                    })
            return db_mappings
        except Exception:
            logger.warning(f"Failed to parse LLM JSON output: {raw_output}")
            return []

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return []
