# Lesson 05: Node-by-node trace (Lab 9 part 1)

Workflow: Webhook → Edit Fields → If → (true) HubSpot lookup (read-only) → Respond 200 / (false) Response 400
Production URL: https://lbabbs.app.n8n.cloud/webhook/demo-request
Date run: 2026-11-27

## Run table

| Event | Exec ID | Edit Fields output (email, source) | If branch | HubSpot lookup (status / total) | Response to curl | Failed node + error |
|---|---|---|---|---|---|---|
| valid-01 |28 |jane.doe@acme.com, website |true |200 / total 0 | 200 | none |
| valid-02 |31 |jane.doe@acme.com, website |true |200 / total 0 | 200 | none |
| valid-03 |32 | same as valid-04 (source: linkedin) | same as valid-04 | same as valid-04 | 200 | none |
| **valid-04 (full detail)** |33 |jane.doe@acme.com, unknown |true |200 / total 0 | 200 (source: unknown) | none |
| valid-05 |34 | same as valid-04 (source: website, event_id: 34) | same as valid-04 | same as valid-04 | 200 | none |
| **invalid-01 (full detail)** |35 |"",website |false | did not run | 400 | none |
| invalid-02 | | same as invalid-01 | same as invalid-01 | did not run | 400 | none |
| invalid-03 | | same as invalid-01 | same as invalid-01 | did not run | 400 | none |
| **fail-401 (full detail)** |38 |jane.doe@acme.com, website |true |401 | 500 Error in workflow |Authentication credentials not found |
| **fail-429, simulated (full detail)** |39 |jane.doe@acme.com, website |true |429 | 500 Error in workflow |Try spacing you requests out |
| **fail-timeout (full detail)** |41 |jane.doe@acme.com,website |true |timeout exceeded 5000ms | 500 Error in workflow |timeout of 5000s exceeded |
| fail-malformed | no execution | did not run | did not run | did not run | 422 Failed to parse request body | n8n webhook front door, before any node |
| restored-valid-01 | | same as valid-04 (source: website) | same as valid-04 | same as valid-04 | 200 | none |

## The 4 failures in my own words
For each: which box failed, who produced the error, what curl saw, what the n8n execution showed.

### 401 (bad token)
The HubSpot lookup node failed. I swapped its credential for a fake token, so HubSpot refused the request and produced the 401: the token wasn't recognized. curl only saw a generic `500 {"message":"Error in workflow"}`, because the workflow stopped at the HubSpot node and never reached a Respond node. The n8n execution (38) showed Webhook, Edit Fields and If green, HubSpot lookup red with the authorization error, and Respond 200 never ran.

### 429 (simulated with httpbin)
The HubSpot lookup node failed. I pointed its URL at httpbin.org/status/429, so httpbin produced the 429, not HubSpot. HubSpot was never called, which is why this one is labeled simulated. curl saw the same generic `500 Error in workflow`. The n8n execution (39) showed every node green up to HubSpot lookup, which was red with a "too many requests" error.

### Timeout
The HubSpot lookup node failed. I pointed it at httpbin.org/delay/10, which waits 10 seconds, but the node's timeout is 5 seconds. No server sent an error code: n8n's own timer gave up first, so n8n produced this failure. curl waited about 5 seconds, then got the generic `500 Error in workflow`. The n8n execution (41) showed HubSpot lookup red with "timeout of 5000ms exceeded".

### Malformed JSON
It failed at n8n's webhook front door, before any node ran. The body was missing its closing brace, so n8n couldn't parse it. n8n produced a 422, and curl saw `422 Failed to parse request body` with a hint pointing to the broken spot. No execution appeared in n8n, because no workflow run ever started. My only evidence is the saved curl response (`runs/fail-malformed.txt`). Lesson: not every failure reaches the orchestrator, so logging the caller's side matters too.

## Other findings

- **valid-05:** The payload had no event_id, but it was accepted with event_id `34`. That value comes from the event_id fallback in Edit Fields, most likely the n8n execution ID (`$execution.id`), since 34 lines up with that run's execution number. This is a dedupe risk: if the same event is sent twice, each run gets a different ID, so duplicates can't be caught. The If node also doesn't check event_id, so missing IDs pass validation. Fix in L06: validate the raw event_id in the If node.
- **Test URL 404 (webhook not registered):** My first test call returned a 404 because the test URL only listens after you click "Execute workflow", and only for one request. n8n produced the 404 at its front door, and no execution appeared because no workflow started. Same category as malformed JSON: a front-door failure the workflow never sees.
