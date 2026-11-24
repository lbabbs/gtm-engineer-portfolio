# HubSpot contacts client

**Results: sandbox-tested against a HubSpot developer test account.**

## What it does
A small Python script that reads contacts from HubSpot's CRM API using a Service Key. It lists contacts, or fetches one by ID, and prints each as `ID | first last | email`.

## What it calls
- List: `GET /crm/v3/objects/contacts` (asks for firstname, lastname, email)
- Single contact: `GET /crm/v3/objects/contacts/{id}`

## What it does on errors
- **401 (bad or missing key):** prints an error and stops. No retry, because retrying with the same bad key fails the same way. *(verify)*
- **404 (contact not found):** prints the error with HubSpot's correlation ID and stops.
- **429 (rate limited):** waits and retries. The wait starts at 5 seconds and doubles each retry (5s, then 10s). Set by `RETRY_DELAY_SECONDS` at the top of the script. *(verify max retries)*

## Logging
Every request is logged to `logs/requests.jsonl` with timestamp, path, status, duration, correlation ID, and rate-limit headers. The key is never logged.

## How to run
1. Set your key in the terminal session: `export HUBSPOT_KEY=your-service-key`. Never commit it.
2. `source .venv/bin/activate`
3. Run one of:
   - `python hubspot_client.py`: list contacts
   - `python hubspot_client.py --limit 5`: list up to 5 (1 to 100)
   - `python hubspot_client.py --id <contact_id>`: get one contact
   - `python hubspot_client.py --burst 200`: send 200 calls in parallel, retries off, to trigger a 429
   - `python hubspot_client.py --simulate-429`: fake two 429s to test the retry delay