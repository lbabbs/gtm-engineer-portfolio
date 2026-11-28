# Lesson 05: Orchestrator vs called API vs CRM storage

## Diagram
![ lesson 5: Architecture Diagram](<Webhook Diagram.jpg>)![ lesson 5: Architecture Diagram](<Screenshot 2026-11-26 at 2.21.40 PM.png>)

## Role table
| Box | Role | Runs on whose server? | Stores data? Where, how long? | Who decides success or failure? |
|---|---|---|---|---|
| curl | Event source | Your local machine (Mac) | Does not store data, unless you save its output (for example with tee) (fixed) | Decides nothing. It only reports the status code n8n responds with (fixed) |
| Webhook | Orchestrator (the trigger) | n8n Cloud server | Stores the node's input and output in the n8n execution record, temporary, per run, about 7 days on Starter (fixed) | n8n. It fails only if the request can't get in: wrong URL, wrong method, or a body it can't read. Whether the data is valid is the If node's call (fixed) |
| Edit Fields | Orchestrator | n8n Cloud server | Stores the node's input and output in the n8n execution record, temporary, per run, about 7 days on Starter (fixed) | n8n. It errors only if an expression breaks. A missing field becomes empty or gets the fallback, which is why the If node exists (fixed) |
| If | Orchestrator | n8n Cloud server | Stores the node's input and output in the n8n execution record, temporary, per run, about 7 days on Starter (fixed) | The If node decides valid vs invalid. Routing to true or false are both successes |
| HTTP Request | Orchestrator: the n8n node that sends the outbound request to the HubSpot API and receives its response (fixed) | n8n Cloud server | Yes: the request and HubSpot's response are saved in the n8n execution record, about 7 days. HTTP is the protocol; this node is a step that runs and gets recorded (fixed) | HubSpot decides, and this node reports its status code. Exception: on a timeout, HubSpot never answers, so n8n's own 5-second timer decides (fixed) |
| HubSpot API | Called API | HubSpot servers | Does not store data. It passes reads and writes to the database (HubSpot may keep its own internal logs) | HubSpot decides, and says so with a status code: 200, 400, 401, 429 (fixed) |
| HubSpot database | CRM storage | HubSpot servers | Stores data permanently, until someone deletes it | HubSpot. It never talks to n8n directly; the API answers for it |

## HubSpot contact count baseline
Count: 3
Date checked: 2026-11-27


## Checkpoint 1

**1. Who produced the 429, and who recorded it?**
- n8n triggered it by sending too many requests in a short period.
- HubSpot produced it: the called API decides what counts as "too many" and responds with the 429.
- n8n recorded it in the execution record, on the HTTP Request node.
- In this lab the 429 is simulated with httpbin, so httpbin produces it. Same rule: whichever server answers produces the status code.
- Short version: n8n triggered it, HubSpot produced it, n8n recorded it.

**2. If n8n deleted every execution, what's lost and what still exists?**
- Lost: the run records for every past run (each node's input and output), which is my debugging trail showing which runs failed and why.
- Still exists: the workflow itself (executions are run records, not the workflow), all contacts in the HubSpot CRM, and anything I saved to GitHub (curl outputs, screenshots).
- This is why I screenshot evidence the same day. Starter keeps executions about 7 days.

**3. Does the search lookup change HubSpot? How would I prove it?**
- No. The search endpoint only reads.
- Proof: compare before and after. The contact count stays at the baseline (3), and one contact's Last modified date doesn't change after the lookups run.
- Note: the search endpoint uses POST and is still read-only. The HTTP verb alone doesn't tell you whether data changes.

**4. Prediction: where does malformed JSON fail, and does an execution appear?**
- Invalid data (readable JSON with bad values) passes Edit Fields, fails the If node and goes to Respond 400.
- Malformed JSON (a broken envelope, like a missing closing brace) can't be parsed into fields, so it most likely fails at the Webhook, before Edit Fields runs. The If node and Respond 400 never get it.
- Does an execution appear? My prediction: ____ (yes or no, fill in before Part 4)
- Actual result (fill in after Part 4):


## Baseline

After 8 test runs, there are still only 3 contacts so this shows us that looking up data in the database does not create new contacts.

Malformed JSON Prediction Question:

- Actual result: 422 from n8n execution did not appear.