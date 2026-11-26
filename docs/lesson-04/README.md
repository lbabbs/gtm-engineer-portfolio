# Lesson 4: Webhooks (Lab 2, part 1)

**Results: sandbox-tested on hosted n8n with synthetic payloads. No real leads.**

**Program:** GTM Engineer Training Program v12.1, builder track, Module 1 (APIs, webhooks and tracing)

**Assignment:** Build an n8n webhook for demo requests. Normalize name, work email, domain, source and intent. Keep person identity separate from the event ID. Reject malformed payloads with a clear response.

**Required evidence:** 5 valid and 3 invalid payloads with their results. See `payloads/` and `results.md`.

**Build:** n8n workflow `L04 Demo Request Webhook`. The export goes in `labs/n8n-demo-webhook/workflow.json`. Lab 2 continues in Lessons 6 and 8 (CRM write, search by stable ID, replay).

## Workflow

```
Webhook (POST /demo-request)
  -> Edit Fields (normalize)
  -> IF (valid?)
       true  -> Respond 200 Accepted
       false -> Response 400 Rejected
```

**Webhook node**
- HTTP Method: POST
- Path: `demo-request`
- Authentication: None (lab only, unpublish after testing)
- Respond: Using 'Respond to Webhook' Node, so the workflow decides between a 200 and a 400

**Edit Fields (normalize)**, with Include Other Input Fields off

| Field | Rule |
|---|---|
| `email` | trim, lowercase |
| `person_id` | same as normalized email |
| `event_id` | sender's event_id, else n8n execution ID |
| `name` | trim, casing preserved (my choice, not a miss) |
| `domain` | part after @ of the normalized email |
| `source` | trim, lowercase, `unknown` if missing or empty |
| `intent` | trim, lowercase |

Every expression starts with `($json.body.field ?? '')` so a missing field gives empty text instead of crashing the node.

**IF node (AND, all must pass)**
- `email` matches `^[^\s@]+@[^\s@]+\.[^\s@]+$`
- `name` is not empty
- `intent` matches `^(demo|pricing|trial)$`

**Responses**
- 200: `status: accepted`, `event_id`, `person_id`
- 400: `status: rejected`, a `message` naming the required fields and allowed intent values, and `event_id`

## Concepts (Explain level)

**Webhooks vs polling**
- Polling: my system asks the source "anything new?" on a schedule. It runs late by up to one interval and wastes API calls when nothing changed.
- Webhook: the source sends data to my URL the moment something happens. It's faster and cheaper, but the URL is open to anyone, so I have to validate and clean everything that comes in.
- For a non-technical audience: "Polling is checking your inbox every 5 minutes. A webhook is getting a text the second something arrives. Anyone can text you, so we screen what comes in."
- Polling still wins when the source has no webhooks, when a daily batch is enough, or as a safety net for missed events.

**Event ID vs person ID**
- Event ID = one submission. It answers "have I already processed this exact request?"
- Person ID = one human. It answers "is this someone I already know?"
- A form retry resends the same event ID, so it's a duplicate. A new submission from the same person gets a new event ID and the same person ID.
- Example: a form sends one submission 3 times because the workflow was slow, then the same person submits again with a new intent. That's 2 event IDs and 1 person ID. The rep should get 2 tasks (or 1 updated task, as a business rule). Never 4.
- The sender should create the event ID. If n8n creates a new one on every run, retries look new and can't be deduped.
- Person ID is built after normalizing. Otherwise `" Jane.Doe@Acme.com "` and `jane.doe@acme.com` become two people and two CRM contacts.

## Design decisions

- **Name casing preserved.** Trim only. Title-casing can damage names like "McDonald" or "de la Cruz".
- **Respond to Webhook instead of Immediately.** "Immediately" would return 200 before validation runs.
- **Missing vs empty are different failure cases.** `??` only catches a missing field. `||` catches missing and empty. `source` and `event_id` use `||` so an empty string still gets a fallback.
- **Rejected responses don't need a trustworthy person_id.** Identity built from invalid input isn't reliable.
- **Work email:** free-mail domains (gmail, yahoo) are accepted for now. Rejecting them would lose real leads. Flagging them is a later improvement.

## Quirks and lessons learned

1. **"Listen for test event" inside the Webhook node runs only that node.** The request returned `HTTP/2 200` with `content-length: 0` because the Respond node never ran. Use **Execute workflow** on the canvas to run the whole flow. A 200 means the door opened, not that the logic ran, so always check the response body too.
2. **Test URL vs production URL.** The test URL (`/webhook-test/`) listens for 120 seconds after clicking Listen and shows data in the editor. The production URL (`/webhook/`) only works after Publish and shows runs in the Executions tab.
3. **Missing-field crashes.** `.trim()` on a missing field breaks the node. A crash is not a rejection: the caller gets an error instead of a clear 400. Fixed with `?? ''` on every field. Proved it by deleting `intent` from pinned data and watching the node fail before the fix.
4. **Normalize first, then derive.** `domain` was first split from the raw email and returned `Acme.com` with a hidden trailing space. Fixed by trimming and lowercasing before the split.
5. **Typos in fallback values become real data.** `source` fell back to `unkonwn`, then `unknownm`. Tests didn't catch it because the test payload had a source. Read fallback strings letter by letter.
6. **Trailing space in a field name.** The `source` field was named `"source "`. Downstream, `$json.source` would find nothing. Field names are matched exactly.
7. **Error messages must match the rule.** The 400 message said "trials" while the IF allowed `trial`. A sender following the message would be rejected again. JSON keys are case-sensitive too, so `Message` was changed to `message` to match the other keys.
8. **Pinned data speeds up building.** Pin the Webhook output to reuse one payload while editing, and edit it (pencil icon) to test failure cases. Unpin before the production run.
9. **`??` lets empty strings through.** A payload with `"event_id": ""` would end up with no event ID. Changed the `event_id` expression to `||`.
10. **`domain` is null on an invalid email.** There's no @ to split on. That's expected, because the IF rejects the payload anyway.

## Test plan

| File | Tests | Expected |
|---|---|---|
| valid-01 | Clean baseline | 200, fields unchanged |
| valid-02 | Messy casing and whitespace | 200, normalized |
| valid-03 | Same person as 01, different casing, new event | 200, same person_id as 01, different event_id |
| valid-04 | No `source` field | 200, source = `unknown` |
| valid-05 | No `event_id` field | 200, fallback event_id |
| invalid-01 | No `email` field | 400, clear message |
| invalid-02 | Email with no @ | 400, clear message |
| invalid-03 | Intent `help` not allowed | 400, clear message |

Results: see `results.md`.

## Still to do

- [x] Change `event_id` to `{{ $json.body.event_id || $execution.id }}` in Edit Fields
- [x] Unpin Webhook data, Publish, run all 8 payloads against the production URL
- [x] Fill in `results.md` (status, response body, execution ID, pass/fail)
- [x] Compare valid-01 and valid-03 responses (same person_id, different event_id)
- [ ] Fix the `essage` typo in Response 400 Rejected, rerun invalid-01 to 03, update results.md
- [ ] Unpublish the workflow
- [ ] Export the workflow to `labs/n8n-demo-webhook/workflow.json`
- [ ] Commit with a message starting `L04:` and link this folder in the tracker

## Docs

- Webhook node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/
- Test vs production URLs: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/workflow-development/
- Respond to Webhook: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook/
- Edit Fields (Set): https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.set/
- IF: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.if/
