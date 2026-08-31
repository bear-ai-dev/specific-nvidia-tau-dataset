# 05 — pharmacy-travel-refill

A patient's albuterol inhaler refill is stuck. The pharmacy app says
"processing"; the real reason is that the payer rejected the claim as a refill
too soon. He lost last month's inhaler in a hotel room, he leaves town in the
morning, and the counter closes in 48 minutes.

Recorded conversation: [`conversations/pharmacy-travel-refill/`](../../conversations/pharmacy-travel-refill).
Domain policy and tool contracts: [`domains/pharmacy/`](../../domains/pharmacy).

| | |
|---|---|
| Domain | pharmacy |
| Scenario time | 2026-08-27T18:12:00-05:00 |
| Tools | 9 |
| Database | PostgreSQL 16, 16 tables and 1 view |

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
docker build -t 05-pharmacy-env environment
docker run -d --name 05-pharmacy 05-pharmacy-env
```

The tool server listens on 127.0.0.1:8080 inside the container, so talk to it
from there. It is ready once `/tmp/task-infra/.ready` exists.

```
docker exec 05-pharmacy curl -s localhost:8080/health
docker exec 05-pharmacy curl -s localhost:8080/tools

docker exec 05-pharmacy curl -s -X POST localhost:8080/tools/lookup_patient \
    -H 'content-type: application/json' \
    -d '{"full_name": "Miles Carter", "date_of_birth": "1988-06-14"}'
```

Two subcommands help while iterating:

```
docker exec 05-pharmacy task-init.sh --reset-db     # rebuild the data, server stays up
docker exec 05-pharmacy task-init.sh --dump-state   # write final state to /out
```

Mount a directory on `/out` to keep the dump. The database itself is reachable
with `docker exec 05-pharmacy psql -U voiceenv -d voiceenv`.
