# Acme Appliances Ledger Agent

A small Flask API that reads `orders.jsonl`, deduplicates by order `id` using latest `updated_at`, and answers common order-ledger aggregation questions.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Send a POST request to `/` with JSON:

```json
{"question":"What was the total revenue in USD from the North region in March 2026?"}
```

## Deploy

Push this folder to a GitHub repository. Create a Render **Web Service** from that repository. Build command: `pip install -r requirements.txt`. Start command: `gunicorn app:app`. The public service URL is the endpoint to submit.

This starter handles common revenue, refund, order-count, customer-count, and unit-sales questions. Test with the actual question patterns before submitting; unusual wording or additional query types may need added parsing logic.
