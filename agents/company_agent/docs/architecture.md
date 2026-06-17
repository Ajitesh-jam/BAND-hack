# Demo-app architecture notes

The checkout API is a FastAPI service under `demo-app/app/`.

## Health endpoint

`GET /health` returns `{"status": "healthy"}` when no chaos is active.
Chaos modes are controlled via `demo-app/app/chaos.py`.

## Common failure modes

- **pool_exhaustion**: simulates DB connection pool exhaustion; checkout returns 503.
- **pii_leak**: error logs contain PII patterns.
- **bad_config**: high error rate on checkout and health.

## Key files

- `app/main.py` — FastAPI app and routes
- `app/chaos.py` — fault injection flags
- `app/checkout.py` — checkout handler (often the fix target)
