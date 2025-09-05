import logging
from uuid import UUID
from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
import os
import httpx

from db_config import (
    init_db,
    close_db, 
    insert_product, 
    insert_control, 
    get_products,
    get_mappings,
    get_connection,
    get_controls,
    get_control_product,
    get_control_text
    )

from mapping import map_all_products, map_two_products
from api_client import APIClient  

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
        access_products = app.state.client.get("/products/request-access/")
        all_products = app.state.client.get("/products/")
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
app.state.client = None
app.state.product_ids = []


async def get_approved_products():
    """Fetch products with approved access from external API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{os.getenv("BASE_URL")}/products/request-access")
        resp.raise_for_status()
        products = resp.json()
        return [p for p in products if p["status"] == "approved"]


async def insert_product_questionnaire(product_id: UUID, product_name: str):
    """
    Fetches questionnaire controls for a product and inserts them into the database.
    Invalid UUIDs are skipped with a warning.
    """
    try:
        # Fetch controls from API
        controls = app.state.client.get(f"/products/{product_id}/questionnaire/")
        print(controls)
        for control in controls:
            control_id_raw = control.get("id")
            text = control.get("text", "")
            metadata = control.get("metadata", {})

            # Safely convert control_id to UUID
            try:
                control_uuid = UUID(control_id_raw)
            except (ValueError, TypeError):
                logger.warning(f"Skipping invalid control ID for product {product_name}: {control_id_raw}")
                continue

            # Insert control
            await insert_control(
                control_id=control_uuid,
                product_id=product_id,
                text=text,
                metadata=metadata
            )

        logger.info(f"✅ Inserted questionnaire for product: {product_name}")

    except Exception as e:
        logger.error(f"Failed to insert questionnaire for product {product_name}: {e}")





@app.get("/percentage/")
async def get_percentage(pool: AsyncConnectionPool = Depends()):
    """
    Returns mapping percentages for approved products only.
    """
    approved_products = await get_approved_products()
    result = {}

    for prod in approved_products:
        pid = prod["product_id"]

        # Fetch total controls for this product
        controls = await get_controls(pid, pool=pool)
        total_controls = len(controls)

        if total_controls == 0:
            result[pid] = 0.0
            continue

        # Fetch how many of its controls are mapped
        mappings = await get_mappings(pid, pool=pool)
        mapped_count = len(mappings)

        percentage = (mapped_count / total_controls) * 100 if total_controls > 0 else 0
        result[pid] = round(percentage, 2)

    return {"approved_products": result}


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



@app.get("/get_sync/{control_id}")
async def get_sync(control_id: str):
    """
    Given a control ID, return all mapped controls from approved products.
    """
    approved_products = await get_approved_products()
    approved_set = set(approved_products)

    mappings = await get_mappings(control_id)

    filtered_mappings = []
    for m in mappings:
        target_product_id = await get_control_product(m["target_id"])
        if target_product_id in approved_set:
            filtered_mappings.append({
                "target_control_id": m["target_id"],
                "target_control_text": await get_control_text(m["target_id"]),
                "confidence": m["score"],
                "product_id": target_product_id,
            })

    return {
        "source_control_id": control_id,
        "mappings": filtered_mappings
    }
