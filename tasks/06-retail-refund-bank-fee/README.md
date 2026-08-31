# 06 — retail-refund-bank-fee

A standing desk converter was returned to a store nine days ago. The return
completed and the item is back in inventory. Forty dollars came back to a gift
card; the 146.42 on the debit card left the register and was never confirmed by
the processor. The customer has been charged an overdraft fee waiting for it.

Recorded conversation: [`conversations/retail-refund-bank-fee/`](../../conversations/retail-refund-bank-fee).
Domain policy and tool contracts: [`domains/retail/`](../../domains/retail).

| | |
|---|---|
| Domain | retail |
| Scenario time | 2026-08-27T13:05:00-04:00 |
| Tools | 9 |
| Database | PostgreSQL 16, 27 tables, 2 views and 1 function |

## What this is

The dataset carries this conversation's tool results as authored JSON, so an
agent that leaves the recorded path has nothing to leave into. Here the records
are a PostgreSQL database and the 9 tools are queries against it: the
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
docker build -t 06-retail-env environment
docker run -d --name 06-retail 06-retail-env
```

The tool server listens on 127.0.0.1:8080 inside the container, so talk to it
from there. It is ready once `/tmp/task-infra/.ready` exists.

```
docker exec 06-retail curl -s localhost:8080/health
docker exec 06-retail curl -s localhost:8080/tools

docker exec 06-retail curl -s -X POST localhost:8080/tools/lookup_customer \
    -H 'content-type: application/json' \
    -d '{"email": "teddy.torrez@harbormail.com"}'
```

Two subcommands help while iterating:

```
docker exec 06-retail task-init.sh --reset-db     # rebuild the data, server stays up
docker exec 06-retail task-init.sh --dump-state   # write final state to /out
```

Mount a directory on `/out` to keep the dump. The database itself is reachable
with `docker exec 06-retail psql -U voiceenv -d voiceenv`.
