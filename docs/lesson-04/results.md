# Lesson 4 results: demo-request webhook

**Results: sandbox-tested on hosted n8n (production URL), synthetic payloads, run Nov 25, 2026.**

Workflow: `L04 Demo Request Webhook`. Payloads in `payloads/`. Command used for each file:

```
curl -s -w "\nHTTP %{http_code}\n\n" -X POST "<production URL>" -H "Content-Type: application/json" -d @<file>.json
```

## Results

| File | Tests | Expected | Status | Response body | Execution ID | Pass |
|---|---|---|---|---|---|---|
| valid-01 | Clean baseline | 200 | 200 | `{"status":"accepted","event_id":"evt_101","person_id":"jane.doe@acme.com"}` | 18 | Yes |
| valid-02 | Messy casing and whitespace | 200, normalized | 200 | `{"status":"accepted","event_id":"evt_102","person_id":"jane.doe@acme.com"}` | 19 | Yes |
| valid-03 | Same person as 01, different casing, new event | 200, same person_id, new event_id | 200 | `{"status":"accepted","event_id":"evt_103","person_id":"jane.doe@acme.com"}` | 20 | Yes |
| valid-04 | No `source` field | 200, source = `unknown` | 200 | `{"status":"accepted","event_id":"evt_104","person_id":"jane.doe@acme.com"}` | 21 | Yes* |
| valid-05 | No `event_id` field | 200, fallback event_id | 200 | `{"status":"accepted","event_id":"22","person_id":"jane.doe@acme.com"}` | 22 | Yes |
| invalid-01 | No `email` field | 400 | 400 | `{"status":"rejected","essage":"Need valid email address, non empty name, and intent of demo,pricing, or trial","event_id":"evt_901"}` | 23 | Yes** |
| invalid-02 | Email with no @ | 400 | 400 | same as invalid-01, `event_id` `evt_902` | 24 | Yes** |
| invalid-03 | Intent `help` not allowed | 400 | 400 | same as invalid-01, `event_id` `evt_903` | 25 | Yes** |

\* The 200 response doesn't include `source`. Confirm `source = unknown` in the Edit Fields output of execution 21.

\*\* Routing and status are correct. In this run the response key was misspelled `essage`. It was fixed to `message` after the run, confirmed in `labs/n8n-demo-webhook/Workflow.json`. Rows 6 to 8 show the output as actually recorded.

**Summary:** 8 of 8 payloads returned the expected status code. 5 accepted, 3 rejected, no node errors.

## What the results prove

**Event ID vs person ID (valid-01 vs valid-03)**
- valid-01: `event_id` `evt_101`, `person_id` `jane.doe@acme.com`
- valid-03: `event_id` `evt_103`, `person_id` `jane.doe@acme.com`
- Same person, two separate events. valid-03 was sent as `JANE.DOE@Acme.com` and still resolved to the same person_id, so normalization runs before identity is computed.

**Normalization (valid-02)**
- Sent as `" Jane.Doe@Acme.com "` with messy casing and spaces, returned `person_id` `jane.doe@acme.com`.

**Fallback event ID (valid-05)**
- No event_id was sent. The response `event_id` is `22`, which matches execution ID 22. The `||` fallback works.

**Rejections (invalid-01 to 03)**
- All three went down the IF false branch and returned 400 with a message naming the requirements.
- n8n marks these runs "Succeeded" because the workflow ran without errors. Rejecting bad input is correct behavior. A real failure would show "Error" with a red node.

## Findings

1. **Typo in the 400 response key: `essage` instead of `message`. Fixed.** Introduced when renaming `Message` to `message`. A system reading `message` would have found nothing. Corrected in Response 400 Rejected after this run (see the workflow export). Lesson 5 reruns all 8 payloads, which will record the corrected response.
2. **The rejection message is the same for every failure.** It lists all requirements but doesn't say which one failed. Acceptable for this lab. A later improvement is a field-specific reason.
