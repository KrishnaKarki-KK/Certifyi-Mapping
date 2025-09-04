import logging
from uuid import UUID
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import os

from db_config import (
    init_db,
    close_db, 
    insert_product, 
    insert_control, 
    get_products,
    get_mappings,
    get_connection,
    get_controls
    )

from mapping import map_all_products, map_two_products
from api_client import APIClient  

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# Global state
app = FastAPI()
app.state.client = None
app.state.product_ids = []  # Approved premium products UUIDs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Async context manager for initializing resources on startup and cleanup.
    """
    try:
        # Initialize DB
        await init_db()
        logger.info("✅ Database initialized")

        # Initialize API client
        app.state.client = APIClient(
            base_url=os.getenv("BASE_URL"),
            email=os.getenv("EMAIL"),
            password=os.getenv("PASSWORD")
        )

        # Fetch approved products
        access_products = await app.state.client.get("/products/request-access/")
        all_products = await app.state.client.get("/products/")
        product_map = {p["id"]: p for p in all_products}

        # Filter approved premium products
        premium_products = []
        for p in access_products:
            if p["status"].lower() != "approved":
                continue
            prod_id = p["product_id"]
            meta = product_map.get(prod_id)
            if meta and not meta.get("is_free", True):
                premium_products.append({"id": prod_id, "name": meta.get("name")})

        # Insert products & their controls
        for product in premium_products:
            pid = UUID(product["id"])
            await insert_product(pid, product["name"])
            # Fetch questionnaire controls
            await insert_product_questionnaire(pid, product["name"])
            app.state.product_ids.append(pid)

        # Initial LLM mapping
        if app.state.product_ids:
            logger.info("🔄 Performing initial batch mapping of all products")
            await map_all_products(app.state.product_ids, threshold=0.85)
            logger.info("✅ Initial mapping completed")

        yield

    finally:
        await close_db()
        logger.info("🛑 Resources closed")


app = FastAPI(lifespan=lifespan)



async def insert_product_questionnaire(product_id: UUID, product_name: str):
    """
    Fetch questionnaire for a product and insert its controls into DB.
    """
    product_data = await app.state.client.get(f"/products/{product_id}/")
    if not product_data or not product_data.get("questionnaire"):
        return  # No controls

    sections = product_data["questionnaire"]
    for section in sections:
        children = section.get("children", [])
        for item in children:
            control_id = item["id"]
            text = item.get("question", "")
            metadata = {
                "type": item.get("type"),
                "description": item.get("description"),
                "section": section.get("question"),
            }
            await insert_control(control_id=UUID(control_id), product_id=product_id, text=text, metadata=metadata)



@app.get("/percentage/")
async def get_percentage():
    """
    Returns mapping percentage for all approved premium products.
    """
    result = {}
    for pid in app.state.product_ids:
        mappings = await get_mappings(pid)
        total_controls = len(await get_controls(pid))
        if total_controls == 0:
            result[str(pid)] = 0
        else:
            mapped_count = len(mappings)
            result[str(pid)] = round(mapped_count / total_controls * 100, 2)
    return result


@app.post("/remap/{product_id}")
async def remap_product(product_id: str):
    """
    Remap a single product against all others.
    """
    pid = UUID(product_id)
    if pid not in app.state.product_ids:
        raise HTTPException(status_code=404, detail="Product not found or not premium")

    await map_all_products([pid] + [p for p in app.state.product_ids if p != pid], threshold=0.85)
    return {"status": "success", "message": f"Product {product_id} remapped"}


@app.get("/get_sync/")
async def get_sync():
    """
    Returns all mappings for sync retrieval.
    """
    from db_config import get_mappings  # reuse function
    result = {}
    for pid in app.state.product_ids:
        mappings = await get_mappings(pid)
        result[str(pid)] = mappings
    return result
