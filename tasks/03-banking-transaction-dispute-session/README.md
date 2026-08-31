# 03 — banking-transaction-dispute-session

A customer sees a 243.18 charge from a merchant he has never heard of, with a
descriptor reading `MRKTPLC*8472` and no city attached. He has the card in his
wallet. The charge is his daughter's patio set, bought through a marketplace
wallet that had his card saved in it, and the right outcome is that no dispute is
ever filed.

Recorded conversation: [`conversations/banking-transaction-dispute-session/`](../../conversations/banking-transaction-dispute-session).
Domain policy and tool contracts: [`domains/banking/`](../../domains/banking).

| | |
|---|---|
| Domain | banking |
| Scenario time | 2026-02-25T16:20:00-05:00 |
| Tools | 16 |
| Database | PostgreSQL 16, 27 tables |

## What this is

The dataset carries this conversation's tool results as authored JSON, so an
agent that leaves the recorded path has nothing to leave into. Here the records
are a PostgreSQL database and the 16 tools are queries against it: the
recorded results come back because the data reproduces them, and a call the
recording never made still gets a truthful answer.

## Layout

```
environment/Dockerfile      postgres 16 and the tool server
environment/task-init.sh    builds the database on boot, then starts the server
environment/sql/            001 schema, 002 catalogs, 003 population, 004 scenario
environment/server/         the REST tool server and its registry
environment/gen_seed.py     author-time generator for 002 and 003
environment/workspace/      the policy the agent works under
```

`sql/004_scenario.sql` is hand-written and holds the entities this conversation
touches. `002` and `003` are generated with a fixed seed; `gen_seed.py` runs at
author time and is kept out of the image by `.dockerignore`.

## Build and run

```
docker build -t 03-banking-env environment
docker run -d --name 03-banking 03-banking-env
```

The tool server listens on 127.0.0.1:8080 inside the container, so talk to it
from there. It is ready once `/tmp/task-infra/.ready` exists.

```
docker exec 03-banking curl -s localhost:8080/health
docker exec 03-banking curl -s localhost:8080/tools

docker exec 03-banking curl -s -X POST localhost:8080/tools/lookup_customer \
    -H 'content-type: application/json' \
    -d '{"full_name": "Justin Porter", "email": "jporter92@email.com"}'
```

Two subcommands help while iterating:

```
docker exec 03-banking task-init.sh --reset-db     # rebuild the data, server stays up
docker exec 03-banking task-init.sh --dump-state   # write final state to /out
```

Mount a directory on `/out` to keep the dump. The database itself is reachable
with `docker exec 03-banking psql -U voiceenv -d voiceenv`.
