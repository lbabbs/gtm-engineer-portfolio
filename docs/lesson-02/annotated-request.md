# Lesson 2: Annotated HubSpot API request

## The request
- Method: GET
  - What it means: Request that is used to retrieve data from a server
- URL: https://api.hubapi.com/crm/v3/objects/contacts/<CONTACT_ID>
  - Base URL (`https://api.hubapi.com`): The URL that the requests are pointing to
  - Path (`/crm/v3/objects/contacts`): The API endpoint for our contact records in version 3 of HubSpot's CRM API.
  - ID at the end: The specific record that is being requested
- Header sent: Authorization: Bearer <SERVICE_KEY>
  - What it does: Prove who you are and which server you have access to, along with what permissions you have to see the information in that server.
  - Why only one scope (crm.objects.contacts.read): One scope so that we don't expose unwanted data and it limits the damage if the key gets exposed.

## The response
- Status line: HTTP/2 200
  - What it means: The request was successful

### Key response headers
- content-type: application/json → The returned info is in JSON format
- x-hubspot-correlation-id → This is a unique ID that HubSpot gives each individual request, so you can track it if necessary.
- x-hubspot-ratelimit-max: 190 and interval-milliseconds: 10000 → The maximum amount of requests in a time period allowed by server
- x-hubspot-ratelimit-remaining: 189 → How many requests you have left in the current 10 second window remaining. after the one that already occured, so 190-1.
- x-hubspot-ratelimit-secondly: 19 and secondly-remaining: 18 → A second limit with 19 requests per second, with 18 remaining after a request goes through.
- x-hubspot-ratelimit-daily / daily-remaining → This is the limit cap of the amount of calls you can send to the server for the entire day.

### JSON body
- id → Record ID
- properties (email, firstname, lastname) → Record Info
- createdAt / updatedAt → Record created time and record updated time
- archived: false → Whether record is archived or not
- Data quirk I noticed: Weird space in the first and last name, whitespace

## What I'd say in an interview
Two or three sentences: what this request does, how it's authenticated, and how you'd know it failed.

This is a GET request to HubSpot's CRM API. It sends a bearer token authenticated with a service key to let the server know which account the request is going to and what scope is allowed. It requests an individual contact ID and it returns that information in JSON. Scoped to read contacts only. I'd know it failed from the status code: 401 means the key is bad, 403 means it lacks permission, 404 means the record doesn't exist, 429 means slow down. The correlation ID lets me trace any failed call.

