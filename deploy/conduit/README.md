# Subject deployment: Conduit (local)

- Upstream: TonyMckes/conduit-realworld-example-app
- Pinned commit: `5e127d8569b300e0a21dc2c20ea680da4967b1aa` (fetched by hash in the Dockerfile; the deployment does not follow upstream)
- Shape: production mode on a single port. `http://localhost:3001` serves both the SPA (HashRouter) and `/api`; Postgres listens on `localhost:5433`.
- Verified at run time (2026-06-10, recorder observation): port 3001 serves the real login page and the SPA build; the login `POST /api/users/login` is issued by the SPA's own code (initiator = script, index-*.js). The upstream dev-mode port 3000 does not exist in this deployment; the SPA and the API share one origin, so the base URL is port 3001.

## Commands

```bash
# start (builds the image on first use)
docker compose up -d --build

# full reset (DROP+CREATE the database -> restart the app -> register the test accounts)
./reset.sh

# stop / remove everything including the data volume
docker compose down
docker compose down -v
```

## Test accounts (registered by reset.sh; overridable through environment variables)

| actor | user-name variable | e-mail variable | password variable |
|---|---|---|---|
| A | `UISEMTEST_CONDUIT_ACTOR_A_USERNAME` | `UISEMTEST_CONDUIT_ACTOR_A_EMAIL` | `UISEMTEST_CONDUIT_ACTOR_A_PASSWORD` |
| B | `UISEMTEST_CONDUIT_ACTOR_B_USERNAME` | `UISEMTEST_CONDUIT_ACTOR_B_EMAIL` | `UISEMTEST_CONDUIT_ACTOR_B_PASSWORD` |

The defaults are local placeholder credentials, not real secrets. The app profile refers to the variable names only.
