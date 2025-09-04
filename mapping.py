import logging
from typing import List, Dict
from uuid import UUID

from db_config import get_connection, insert_mapping, get_controls
from model import map_product_controls_with_llm

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def fetch_product_controls(product_id: UUID) -> Dict:
    """
    Fetch a product and all its controls from the DB.
    Returns a dict with:
    {
        "id": <product_id>,
        "controls": [{"id": <control_id>, "text": <text>, "metadata": {...}}, ...]
    }
    """
    controls = await get_controls(product_id)
    return {
        "id": product_id,
        "controls": controls
    }


async def insert_mappings_to_db(mappings: List[Dict], threshold: float = 0.8):
    """
    Insert LLM mappings into the DB if confidence >= threshold.
    Also inserts reverse mapping.
    """
    if not mappings:
        return

    for m in mappings:
        if m["confidence"] >= threshold:
            try:
                await insert_mapping(
                    source_id=UUID(m["source_id"]),
                    target_id=UUID(m["target_id"]),
                    confidence=m["confidence"]
                )
                # Insert reverse mapping
                await insert_mapping(
                    source_id=UUID(m["target_id"]),
                    target_id=UUID(m["source_id"]),
                    confidence=m["confidence"]
                )
            except Exception as e:
                logger.error(f"❌ Failed to insert mapping {m}: {e}")


async def map_two_products(product_a_id: UUID, product_b_id: UUID, threshold: float = 0.8):
    """
    Map all controls between two products in **one LLM call**.
    """
    product_a = await fetch_product_controls(product_a_id)
    product_b = await fetch_product_controls(product_b_id)

    if not product_a["controls"] or not product_b["controls"]:
        logger.warning(f"⚠️ No controls to map for products {product_a_id} or {product_b_id}")
        return

    logger.info(f"🔄 Mapping products {product_a_id} ↔ {product_b_id}")

    # Call the LLM to map all controls at once
    mappings = await map_product_controls_with_llm(product_a, product_b)

    await insert_mappings_to_db(mappings, threshold=threshold)
    logger.info(f"✅ Completed mapping {product_a_id} ↔ {product_b_id}")


async def map_all_products(product_ids: List[UUID], threshold: float = 0.8):
    """
    Map all products pairwise.
    """
    n = len(product_ids)
    for i in range(n):
        for j in range(i + 1, n):
            await map_two_products(product_ids[i], product_ids[j], threshold)
