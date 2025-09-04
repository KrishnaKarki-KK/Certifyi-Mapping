import logging
from uuid import UUID
from psycopg_pool import AsyncConnectionPool
import os
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Database URL
DATABASE_URL = f"postgresql://{os.getenv("DB_USER")}:@{os.getenv("DB_HOST")}:/{os.getenv("DB_NAME")}"

# Global pool
pool: AsyncConnectionPool | None = None


async def init_db():
    """
    Initialize connection pool and database schema.
    """
    global pool
    pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        min_size=5,
        max_size=40,
        max_lifetime=1800,
        max_idle=300,
        timeout=30,
    )

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # Products table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id UUID PRIMARY KEY,
                    name TEXT NOT NULL,
                    metadata JSONB
                );
            """)

            # Controls table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS controls (
                    id UUID PRIMARY KEY,
                    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    metadata JSONB
                );
            """)

            # Mappings table
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS mappings (
                    id SERIAL PRIMARY KEY,
                    source_control_id UUID REFERENCES controls(id) ON DELETE CASCADE,
                    target_control_id UUID REFERENCES controls(id) ON DELETE CASCADE,
                    confidence FLOAT NOT NULL,
                    UNIQUE (source_control_id, target_control_id)
                );
            """)

            # Indexes for faster lookups
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_controls_product_id ON controls(product_id);")
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_mappings_source_id ON mappings(source_control_id);")
        await conn.commit()

    logger.info("✅ Database initialized with tables and indexes")


async def get_connection():
    if pool is None:
        raise RuntimeError("Database pool is not initialized")
    return pool.connection()


async def close_db():
    global pool
    if pool is not None:
        await pool.close()
        pool = None
        logger.info("🛑 Database connection closed")



async def insert_product(product_id: UUID, name: str, metadata: dict = None):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO products (id, name, metadata)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING;
            """, (product_id, name, metadata or {}))
        await conn.commit()


async def get_products():
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, name, metadata FROM products;")
            rows = await cur.fetchall()
    return [{"id": r[0], "name": r[1], "metadata": r[2]} for r in rows]



async def insert_control(control_id: UUID, product_id: UUID, text: str, metadata: dict = None):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO controls (id, product_id, text, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, metadata = EXCLUDED.metadata;
            """, (control_id, product_id, text, metadata or {}))
        await conn.commit()


async def get_controls(product_id: UUID):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT id, text, metadata FROM controls WHERE product_id = %s;
            """, (product_id,))
            rows = await cur.fetchall()
    return [{"id": r[0], "text": r[1], "metadata": r[2]} for r in rows]



async def insert_mapping(source_id: UUID, target_id: UUID, confidence: float):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO mappings (source_control_id, target_control_id, confidence)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_control_id, target_control_id) DO NOTHING;
            """, (source_id, target_id, confidence))
        await conn.commit()


async def get_mappings(source_id: UUID):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT target_control_id, confidence
                FROM mappings
                WHERE source_control_id = %s
                ORDER BY confidence DESC;
            """, (source_id,))
            rows = await cur.fetchall()
    return [{"target_id": r[0], "score": r[1]} for r in rows]
