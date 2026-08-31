# 02 — banking-referral-missing-reward

A customer referred his sister, she was approved, and the hundred-dollar bonus
has not arrived. The app has said "pending" for three checks. Approval and
qualification turn out to be different stages, the stage he is stuck on belongs
to an account he has no right to see, and the banner he read set an expectation
the terms never made.

Recorded conversation: [`conversations/banking-referral-missing-reward/`](../../conversations/banking-referral-missing-reward).
Domain policy and tool contracts: [`domains/banking/`](../../domains/banking).

| | |
|---|---|
| Domain | banking |
| Scenario time | 2026-08-28T09:09:00-04:00 |
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
docker build -t 02-banking-env environment
docker run -d --name 02-banking 02-banking-env
```

The tool server listens on 127.0.0.1:8080 inside the container, so talk to it
from there. It is ready once `/tmp/task-infra/.ready` exists.

```
docker exec 02-banking curl -s localhost:8080/health
docker exec 02-banking curl -s localhost:8080/tools

docker exec 02-banking curl -s -X POST localhost:8080/tools/lookup_customer \
    -H 'content-type: application/json' \
    -d '{"email": "daniel.brooks17@gmail.com"}'
```

Two subcommands help while iterating:

```
docker exec 02-banking task-init.sh --reset-db     # rebuild the data, server stays up
docker exec 02-banking task-init.sh --dump-state   # write final state to /out
```

Mount a directory on `/out` to keep the dump. The database itself is reachable
with `docker exec 02-banking psql -U voiceenv -d voiceenv`.
