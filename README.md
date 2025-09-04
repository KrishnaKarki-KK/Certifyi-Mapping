# Compliance Product Mapping API

This project provides a **production-ready system** for mapping compliance controls across multiple products using **LLM-based mapping**, storing data in PostgreSQL, and exposing endpoints to retrieve mapping percentages and synchronized control mappings. It supports **premium products only**, handles **UUID-based IDs**, and is fully **async and scalable**.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Database Setup](#database-setup)
5. [Environment Variables](#environment-variables)
6. [Running the Application](#running-the-application)
7. [API Endpoints](#api-endpoints)
8. [Notes & Recommendations](#notes--recommendations)

---

## Features

* Initialize PostgreSQL DB and tables asynchronously (`products`, `controls`, `mappings`)
* Insert questionnaires from products automatically
* Map **all controls of a product to another** using **LLM**
* Store mappings with confidence scores
* Reverse mappings automatically inserted
* Compute mapping percentage per product
* Async context manager for **resource initialization and cleanup**
* Production-ready for **10k+ concurrent users**

---

## Requirements

* Python 3.11+
* PostgreSQL 14+
* pip packages:

```text
fastapi
uvicorn
psycopg[binary]
psycopg_pool
openai
requests
python-dotenv
```

---

## Installation

1. Clone the repository:

```bash
git clone <repo-url>
cd <repo-folder>
```

2. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Database Setup

1. Start PostgreSQL and create the database:

```sql
-- Connect to postgres
CREATE DATABASE mapping;
-- Optional: create a user or use existing one with privileges
```

2. The application will **initialize tables automatically** (`products`, `controls`, `mappings`) with correct constraints and UUIDs.

3. Optional: Add indexes for performance:

```sql
CREATE INDEX IF NOT EXISTS idx_controls_product_id ON controls(product_id);
CREATE INDEX IF NOT EXISTS idx_mappings_source_id ON mappings(source_control_id);
```

---

## Environment Variables

Create a `.env` file in the project root with the following variables:

```text
# OpenAI API Key
OPENAI_API_KEY=""

# API Client
BASE_URL=""
EMAIL=""
PASSWORD=""

# Database Configurations
DB_NAME=""
DB_USER=""
DB_PASSWORD=""
DB_HOST=""  # e.g., localhost
DB_PORT=""
```

> These variables are required for LLM mapping, API access, and database connection.

---

## Running the Application

1. Start the FastAPI server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

2. On startup, the server will:

* Initialize the database and tables
* Fetch **approved premium products** from the API
* Insert controls from the product questionnaire
* Perform **initial batch LLM mapping**

3. Visit the interactive API docs:

```
http://localhost:8000/docs
```

---

## API Endpoints

| Method | Path                  | Description                                                  |
| ------ | --------------------- | ------------------------------------------------------------ |
| GET    | `/percentage/`        | Returns mapping percentage for all approved premium products |
| POST   | `/remap/{product_id}` | Remaps a single product against all others                   |
| GET    | `/get_sync/`          | Retrieves all mappings for sync retrieval                    |

---

## Notes & Recommendations

* **Mapping Threshold**: Currently defaults to `0.85`. Adjust in `mapping.py` if needed.
* **Scalability**: Async DB connections + async LLM calls support thousands of concurrent products.
* **LLM**: Uses `gpt-4o-mini`. Ensure your OpenAI quota is sufficient for batch mapping.
* **Error Handling**: Logs all errors. Failed mappings are skipped without blocking other operations.
* **New Products**: Use `/remap/{product_id}` to map new products after adding them.

---

### Example

```bash
# Get mapping percentage for all products
curl http://localhost:8000/percentage/

# Remap a product by UUID
curl -X POST http://localhost:8000/remap/<product_uuid>

# Retrieve all mappings
curl http://localhost:8000/get_sync/
```

**Project is now ready for production use with fast async operations, UUID-based controls, and LLM-powered mapping.**
