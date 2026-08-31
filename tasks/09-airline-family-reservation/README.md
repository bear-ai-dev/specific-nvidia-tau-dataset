# 09 — airline-family-reservation

A grandmother is booking two nonstop seats from Phoenix to Washington for
herself and her twelve-year-old grandson. She is travelling with a folding
walker, the website offered her three Washington airports and she does not know
which one she needs, and she has a travel certificate she thinks is worth $200.
Nothing may be quoted that the backend has not computed, and nothing charged that
she has not authorized.

Recorded conversation: [`conversations/airline-family-reservation/`](../../conversations/airline-family-reservation).
Domain policy and tool contracts: [`domains/airline/`](../../domains/airline).

| | |
|---|---|
| Domain | airline |
| Scenario time | 2026-08-26T12:30:00-07:00 |
| Tools | 9 |
| Database | PostgreSQL 16, 27 tables and 1 view |

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
docker build -t 09-airline-env environment
docker run -d --name 09-airline 09-airline-env
```

The tool server listens on 127.0.0.1:8080 inside the container, so talk to it
from there. It is ready once `/tmp/task-infra/.ready` exists.

```
docker exec 09-airline curl -s localhost:8080/health
docker exec 09-airline curl -s localhost:8080/tools

docker exec 09-airline curl -s -X POST localhost:8080/tools/list_supported_airports \
    -H 'content-type: application/json' \
    -d '{"destination_area": "National Mall, Washington, DC"}'
```

Two subcommands help while iterating:

```
docker exec 09-airline task-init.sh --reset-db     # rebuild the data, server stays up
docker exec 09-airline task-init.sh --dump-state   # write final state to /out
```

Mount a directory on `/out` to keep the dump. The database itself is reachable
with `docker exec 09-airline psql -U voiceenv -d voiceenv`.
