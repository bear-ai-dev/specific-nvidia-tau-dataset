# 10 — telecom-data-usage-cleanup

A caller wakes to an alert saying he has used 85% of his data, and he was asleep
while it happened. The carrier metered 11.8 GB on his line between midnight and
four in the morning. He has 2.2 GB of high-speed data left, nine days of cycle to
spend it in, and a work trip before then.

Recorded conversation: [`conversations/telecom-data-usage-cleanup/`](../../conversations/telecom-data-usage-cleanup).
Domain policy and tool contracts: [`domains/telecom/`](../../domains/telecom).

| | |
|---|---|
| Domain | telecom |
| Scenario time | 2026-08-27T19:30:00-05:00 |
| Tools | 8 |
| Database | PostgreSQL 16, 21 tables, 1 view and 4 functions |

## What this is

The dataset carries this conversation's tool results as authored JSON, so an
agent that leaves the recorded path has nothing to leave into. Here the records
are a PostgreSQL database and the 8 tools are queries against it: the
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
docker build -t 10-telecom-env environment
docker run -d --name 10-telecom 10-telecom-env
```

The tool server listens on 127.0.0.1:8080 inside the container, so talk to it
from there. It is ready once `/tmp/task-infra/.ready` exists.

```
docker exec 10-telecom curl -s localhost:8080/health
docker exec 10-telecom curl -s localhost:8080/tools

docker exec 10-telecom curl -s -X POST localhost:8080/tools/lookup_customer \
    -H 'content-type: application/json' \
    -d '{"mobile_number": "404-555-0176", "full_name": "Benjamin Reed", "date_of_birth": "November 22, 1991"}'
```

Two subcommands help while iterating:

```
docker exec 10-telecom task-init.sh --reset-db     # rebuild the data, server stays up
docker exec 10-telecom task-init.sh --dump-state   # write final state to /out
```

Mount a directory on `/out` to keep the dump. The database itself is reachable
with `docker exec 10-telecom psql -U voiceenv -d voiceenv`.
