"""
A small HubSpot contacts client that uses the plain REST API (no HubSpot SDK).

Usage:
    export HUBSPOT_KEY=your-service-key
    python hubspot_client.py --limit 5            # list up to 5 contacts
    python hubspot_client.py --id 12345           # get one contact by ID
    python hubspot_client.py --burst 200          # 200 calls, 20 in parallel, no retries
    python hubspot_client.py --simulate-429       # first 2 attempts act like a 429

Retries (up to 3 attempts in total):
    429 rate limited    wait 5s, then 10s (RETRY_DELAY_SECONDS, doubling),
                        or the Retry-After header if HubSpot sends one
    network / 5xx       wait a fixed 2s (NETWORK_AND_SERVER_RETRY_DELAY_SECONDS)
    other errors        no retry

Every request is written as one JSON line to logs/requests.jsonl.
The service key is never written to the log.
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests


# ---------------------------------------------------------------------------
# Config: change these by hand if you need to
# ---------------------------------------------------------------------------

BASE_URL = "https://api.hubapi.com"
CONTACTS_PATH = "/crm/v3/objects/contacts"
PROPERTIES = "firstname,lastname,email"

TIMEOUT_SECONDS = 10
MAX_RETRIES = 3

# Wait before retrying a 429 (rate limited). Doubles on each retry: 5s, then 10s.
# If HubSpot sends a Retry-After header, that value is used instead.
RETRY_DELAY_SECONDS = 5

# Fixed wait before retrying a network error or a 5xx server error.
NETWORK_AND_SERVER_RETRY_DELAY_SECONDS = 2

# How many --burst requests are in flight at the same time.
BURST_PARALLEL_REQUESTS = 20

# The log file sits next to this script, wherever you run it from.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "logs", "requests.jsonl")

# Status codes worth trying again, because the problem is usually temporary.
RETRYABLE_SERVER_ERRORS = [500, 502, 503, 504]

# How many fake 429 responses are still to come. main() sets this to 2 when
# --simulate-429 is used; send_request counts it down. 0 means "off".
simulated_429s_left = 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class HubSpotError(Exception):
    """Raised when a request to HubSpot fails in a way we can't recover from."""

    def __init__(self, message, status_code=None, correlation_id=None):
        if correlation_id:
            message = message + " (correlation id " + correlation_id + ")"
        super().__init__(message)
        self.status_code = status_code
        self.correlation_id = correlation_id


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_request(method, path, status, duration_ms, response):
    """
    Append one JSON line describing a request to the log file.

    Only the fields listed below are written. Request headers are never
    logged, so the Authorization header (the service key) can't end up here.
    `response` is None when the request failed before HubSpot answered.
    """
    if response is not None:
        headers = response.headers
    else:
        headers = {}

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": path,
        "status": status,
        "duration_ms": duration_ms,
        "correlation_id": headers.get("X-HubSpot-Correlation-Id"),
        "ratelimit_remaining": headers.get("X-HubSpot-RateLimit-Remaining"),
        "ratelimit_secondly_remaining": headers.get("X-HubSpot-RateLimit-Secondly-Remaining"),
    }

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(json.dumps(entry) + "\n")


def log_simulated_429(method, path, attempt, wait_seconds):
    """
    Append one JSON line for a fake 429 attempt (no request was sent).

    Records the timestamp, the status and how long the script will wait
    before the next attempt (0 if there is no next attempt).
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": path,
        "attempt": attempt,
        "status": 429,
        "simulated": True,
        "wait_seconds": wait_seconds,
    }

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Helpers for reading HubSpot error responses
# ---------------------------------------------------------------------------

def read_error_body(response):
    """Return the JSON error body as a dict, or an empty dict if it isn't JSON."""
    try:
        body = response.json()
    except ValueError:
        return {}
    if isinstance(body, dict):
        return body
    return {}


def find_required_scopes(error_body):
    """
    Look for the scopes HubSpot says are missing.

    HubSpot puts them inside error_body["errors"][...]["context"], under
    "requiredGranularScopes" or "requiredScopes". Returns a list of strings.
    """
    scopes = []
    for error in error_body.get("errors", []):
        context = error.get("context", {})
        for key in ["requiredGranularScopes", "requiredScopes"]:
            for scope in context.get(key, []):
                if scope not in scopes:
                    scopes.append(scope)
    return scopes


# ---------------------------------------------------------------------------
# The request function: retries, logging and error handling all live here
# ---------------------------------------------------------------------------

def send_request(session, path, params, not_found_message):
    """
    Send a GET request to HubSpot and return the parsed JSON body.

    Retries network errors, 429 (rate limited) and 5xx errors up to
    MAX_RETRIES times. Any other error raises HubSpotError straight away.
    """
    url = BASE_URL + path
    last_problem = "no attempts were made"
    last_status = None
    last_correlation_id = None

    global simulated_429s_left

    for attempt in range(1, MAX_RETRIES + 1):
        # 0. With --simulate-429, pretend HubSpot rate limited us. Nothing
        #    is sent to HubSpot for these attempts.
        if simulated_429s_left > 0:
            simulated_429s_left = simulated_429s_left - 1
            if attempt < MAX_RETRIES:
                # Doubles each time: attempt 1 waits 5s, attempt 2 waits 10s.
                wait_seconds = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            else:
                wait_seconds = 0
            log_simulated_429("GET", path, attempt, wait_seconds)
            last_problem = "429: simulated rate limit"
            last_status = 429
            last_correlation_id = None
            print("Attempt " + str(attempt) + " got a simulated 429. Waiting "
                  + str(wait_seconds) + "s.", file=sys.stderr)
            time.sleep(wait_seconds)
            continue

        start = time.monotonic()

        # 1. Send the request. Network problems mean HubSpot never answered.
        try:
            response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except (requests.ConnectionError, requests.Timeout) as error:
            duration_ms = round((time.monotonic() - start) * 1000)
            log_request("GET", path, None, duration_ms, None)
            last_problem = "network error: " + type(error).__name__
            last_status = None
            last_correlation_id = None
            print("Attempt " + str(attempt) + " failed (" + last_problem + ").", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(NETWORK_AND_SERVER_RETRY_DELAY_SECONDS)
            continue

        # 2. HubSpot answered, so log it. response.request.path_url is the
        #    path plus query string, e.g. /crm/v3/objects/contacts?limit=5
        duration_ms = round((time.monotonic() - start) * 1000)
        status = response.status_code
        correlation_id = response.headers.get("X-HubSpot-Correlation-Id")
        log_request("GET", response.request.path_url, status, duration_ms, response)

        # 3. Decide what to do based on the status code.
        if status == 200:
            try:
                return response.json()
            except ValueError:
                raise HubSpotError(
                    "200: HubSpot sent a response that isn't valid JSON.",
                    status, correlation_id,
                )

        elif status == 429:
            # Rate limited. Wait as long as HubSpot asks, if it says.
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None and retry_after.isdigit():
                wait_seconds = int(retry_after)
            else:
                # Doubles each time: attempt 1 waits 5s, attempt 2 waits 10s.
                wait_seconds = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            last_problem = "429: rate limited by HubSpot"
            last_status = status
            last_correlation_id = correlation_id
            print("Attempt " + str(attempt) + " was rate limited.", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(wait_seconds)

        elif status in RETRYABLE_SERVER_ERRORS:
            last_problem = str(status) + ": HubSpot server error"
            last_status = status
            last_correlation_id = correlation_id
            print("Attempt " + str(attempt) + " got a " + str(status) + " server error.", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(NETWORK_AND_SERVER_RETRY_DELAY_SECONDS)

        elif status == 401:
            raise HubSpotError(
                "401: the service key is invalid or expired.",
                status, correlation_id,
            )

        elif status == 403:
            error_body = read_error_body(response)
            category = error_body.get("category", "unknown")
            scopes = find_required_scopes(error_body)
            if scopes:
                scopes_text = ", ".join(scopes)
            else:
                scopes_text = "not given"
            raise HubSpotError(
                "403: the service key is not allowed to do this (category: "
                + category + "). Required scopes: " + scopes_text + ".",
                status, correlation_id,
            )

        elif status == 404:
            raise HubSpotError("404: " + not_found_message, status, correlation_id)

        else:
            # Any other error (400, 405, ...) won't fix itself, so don't retry.
            error_body = read_error_body(response)
            message = error_body.get("message", "unexpected error from HubSpot")
            raise HubSpotError(str(status) + ": " + message, status, correlation_id)

    # We only get here if every attempt hit a retryable problem.
    raise HubSpotError(
        "Gave up after " + str(MAX_RETRIES) + " attempts. Last problem: " + last_problem,
        last_status, last_correlation_id,
    )


# ---------------------------------------------------------------------------
# Contact functions
# ---------------------------------------------------------------------------

def get_contact(session, contact_id):
    """Fetch one contact by its HubSpot ID and return it as a dict."""
    path = CONTACTS_PATH + "/" + str(contact_id)
    params = {"properties": PROPERTIES}
    not_found_message = "contact " + str(contact_id) + " not found."
    return send_request(session, path, params, not_found_message)


def list_contacts(session, limit):
    """
    Fetch one page of contacts, up to `limit` (HubSpot allows 1 to 100).

    Only the first page is returned. Pagination comes later (Module 2).
    """
    if limit < 1 or limit > 100:
        raise HubSpotError("limit must be between 1 and 100, got " + str(limit) + ".")
    params = {"limit": limit, "properties": PROPERTIES}
    body = send_request(session, CONTACTS_PATH, params, "contacts endpoint not found.")
    return body.get("results", [])


def run_burst(session, count, limit):
    """
    Call the list-contacts endpoint `count` times as fast as possible,
    with BURST_PARALLEL_REQUESTS calls running at the same time.

    Used to watch HubSpot's rate limit. Retries are turned off on purpose:
    each call is sent once, logged, and printed, whatever the status.
    It sends requests directly instead of using send_request, because
    send_request always retries.
    """
    if count < 1:
        raise HubSpotError("--burst must be at least 1, got " + str(count) + ".")
    if limit < 1 or limit > 100:
        raise HubSpotError("limit must be between 1 and 100, got " + str(limit) + ".")

    url = BASE_URL + CONTACTS_PATH
    params = {"limit": limit, "properties": PROPERTIES}

    # A requests.Session isn't safe to share between threads, so each call
    # uses plain requests.get with a copy of the session's headers.
    headers = dict(session.headers)

    # Only one thread at a time may write to the log file or the screen,
    # so lines from different calls don't get mixed together.
    output_lock = threading.Lock()

    def send_one_call(call_number):
        """Send a single burst call (no retries), then log and print it."""
        timestamp = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()

        try:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_SECONDS)
        except (requests.ConnectionError, requests.Timeout) as error:
            duration_ms = round((time.monotonic() - start) * 1000)
            with output_lock:
                log_request("GET", CONTACTS_PATH, None, duration_ms, None)
                print(timestamp + " | call " + str(call_number) + " | network error: "
                      + type(error).__name__ + " | remaining: -")
            return

        # log_request writes the timestamp, status and rate-limit headers
        # to logs/requests.jsonl. Request headers (the key) are never logged.
        duration_ms = round((time.monotonic() - start) * 1000)
        remaining = response.headers.get("X-HubSpot-RateLimit-Remaining", "-")
        with output_lock:
            log_request("GET", response.request.path_url, response.status_code, duration_ms, response)
            print(timestamp + " | call " + str(call_number) + " | status "
                  + str(response.status_code) + " | remaining: " + remaining)

    # Keep BURST_PARALLEL_REQUESTS calls in flight at once. Calls finish in
    # any order, so the output is not sorted by call number.
    with ThreadPoolExecutor(max_workers=BURST_PARALLEL_REQUESTS) as pool:
        futures = []
        for call_number in range(1, count + 1):
            futures.append(pool.submit(send_one_call, call_number))
        for future in futures:
            future.result()  # re-raises any unexpected error from a call


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def print_contact(contact):
    """Print one contact as: id | first last | email"""
    properties = contact.get("properties", {})
    # A missing or empty name becomes "", then surrounding spaces are removed.
    first_name = (properties.get("firstname") or "").strip()
    last_name = (properties.get("lastname") or "").strip()
    email = properties.get("email") or "(no email)"
    full_name = (first_name + " " + last_name).strip() or "(no name)"
    print(contact.get("id", "?") + " | " + full_name + " | " + email)


def main():
    parser = argparse.ArgumentParser(description="Read contacts from HubSpot.")
    parser.add_argument("--limit", type=int, default=10, help="how many contacts to list (1-100)")
    parser.add_argument("--id", help="get a single contact by ID instead of listing")
    parser.add_argument("--burst", type=int, metavar="N",
                        help="call list-contacts N times as fast as possible, no retries")
    parser.add_argument("--simulate-429", action="store_true",
                        help="pretend the first 2 attempts got a 429, then make the real call")
    args = parser.parse_args()

    if args.simulate_429:
        global simulated_429s_left
        simulated_429s_left = 2

    service_key = os.environ.get("HUBSPOT_KEY")
    if not service_key:
        print("HUBSPOT_KEY is not set. Add your HubSpot service key to the environment.", file=sys.stderr)
        sys.exit(1)

    # The key only ever lives in this header. It is never logged.
    session = requests.Session()
    session.headers["Authorization"] = "Bearer " + service_key

    try:
        if args.burst is not None:
            run_burst(session, args.burst, args.limit)
        elif args.id:
            contact = get_contact(session, args.id)
            print_contact(contact)
        else:
            contacts = list_contacts(session, args.limit)
            if not contacts:
                print("No contacts found.")
            for contact in contacts:
                print_contact(contact)
    except HubSpotError as error:
        print("Error: " + str(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
