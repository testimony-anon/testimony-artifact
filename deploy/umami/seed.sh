#!/usr/bin/env bash
# docker_single `seed` hook for Umami.  Runs after `supervise` starts the
# application container and again after every reset.
#
# First call (no golden template yet):
#   * create actor_b through the public REST API (the image bootstraps exactly
#     one account, which is actor_a);
#   * create the fixed websites and the fixed team that the recording workflows
#     in fixtures/recording_workflows/umami_modular/ take as their baseline,
#     all with literal ids so every workflow can name them;
#   * freeze the result as the template database `umami_golden`.
# Every later call is a marker-file check and returns in a few milliseconds,
# because deploy/umami/reset.sh has already restored that template.
#
# Anything seeded here is "setup that the official spec did through
# APIRequestContext" (helpers.addWebsite / session-modal-dismiss.createWebsite)
# or a fixed literal that replaces a value the spec generated at run time
# (a random uuid, a server-generated team access code).  See
# fixtures/recording_workflows/umami_modular/origin.json for the per-case mapping.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/lib.sh"
umami_resolve_names

[ -f "$UMAMI_GOLDEN_MARKER" ] && exit 0

: "${UISEMTEST_UMAMI_ACTOR_A_USERNAME:?}" "${UISEMTEST_UMAMI_ACTOR_A_PASSWORD:?}"
: "${UISEMTEST_UMAMI_ACTOR_B_USERNAME:?}" "${UISEMTEST_UMAMI_ACTOR_B_PASSWORD:?}"

UMAMI_BASE_URL="$UMAMI_BASE_URL" python3 - <<'PY'
import json, os, sys, urllib.error, urllib.request

BASE = os.environ["UMAMI_BASE_URL"]


def call(method, path, body=None, token=None, tolerate=()):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        if error.code in tolerate:      # already seeded is not a seed failure
            return None
        raise


def login(password):
    return call("POST", "/api/auth/login",
                {"username": os.environ["UISEMTEST_UMAMI_ACTOR_A_USERNAME"],
                 "password": password},
                tolerate=(401,))


# The image bootstraps actor_a with a fixed default password.  That default is a
# single dictionary word that also occurs inside this subject's own identifiers
# (workflow ids, profile paths, reset epochs), and Stage 1 redacts every secret
# string it finds anywhere in a bundle -- which silently rewrote those
# identifiers and broke the suite's bundle-closure check.  So the first seed
# immediately replaces it with the value from .env, and every later seed logs in
# with that value directly.
IMAGE_BOOTSTRAP_PASSWORD = "umami"
actor_a_password = os.environ["UISEMTEST_UMAMI_ACTOR_A_PASSWORD"]
session = login(actor_a_password)
if session is None:
    session = login(IMAGE_BOOTSTRAP_PASSWORD)
    if session is None:
        sys.exit("actor_a accepts neither the .env password nor the image default")
    account = call("POST", "/api/auth/verify", token=session["token"])
    call("POST", f"/api/users/{account['id']}",
         {"password": actor_a_password}, token=session["token"])
    session = login(actor_a_password)
    if session is None:
        sys.exit("actor_a password rotation did not take effect")
token = session["token"]

call("POST", "/api/users",
     {"id": "b0000000-0000-4000-8000-000000000002",
      "username": os.environ["UISEMTEST_UMAMI_ACTOR_B_USERNAME"],
      "password": os.environ["UISEMTEST_UMAMI_ACTOR_B_PASSWORD"],
      "role": "user"},
     token=token, tolerate=(400, 409))

# Fixed ids so a workflow can navigate straight to /websites/<id>/settings.
WEBSITES = [
    ("a0000000-0000-4000-8000-000000000001", "Survey Site", "survey.example"),
    ("a0000000-0000-4000-8000-000000000002", "Update test", "updatetest.com"),
    ("a0000000-0000-4000-8000-000000000003", "Delete test", "deletetest.com"),
    ("a0000000-0000-4000-8000-000000000004", "Modal dismiss test", "modal-dismiss-test.com"),
    ("a0000000-0000-4000-8000-000000000005", "Carver Site", "carver.example"),
]
for website_id, name, domain in WEBSITES:
    call("POST", "/api/websites", {"id": website_id, "name": name, "domain": domain},
         token=token, tolerate=(400, 409))

# POST /api/teams generates the access code itself; seed.sh pins it below with
# SQL so a join-a-team workflow can carry it as a literal.
call("POST", "/api/teams", {"name": "Carver Team"}, token=token, tolerate=(400, 409))
PY

umami_psql "$UMAMI_DB_NAME" \
  -c "UPDATE team SET access_code = 'team_carverflow0001' WHERE name = 'Carver Team';" >/dev/null

# Freeze the seeded state as a template database.  datallowconn=false closes the
# window in which the application's Prisma pool could reconnect between the
# terminate and the CREATE ... TEMPLATE.
umami_psql postgres \
  -c "DROP DATABASE IF EXISTS ${UMAMI_DB_GOLDEN} WITH (FORCE);" \
  -c "UPDATE pg_database SET datallowconn = false WHERE datname = '${UMAMI_DB_NAME}';" \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${UMAMI_DB_NAME}';" \
  -c "CREATE DATABASE ${UMAMI_DB_GOLDEN} TEMPLATE ${UMAMI_DB_NAME};" \
  -c "UPDATE pg_database SET datallowconn = true WHERE datname = '${UMAMI_DB_NAME}';" >/dev/null

mkdir -p "$UMAMI_RUNTIME_DIR"
: > "$UMAMI_GOLDEN_MARKER"
echo "seeded and froze ${UMAMI_DB_GOLDEN}"
