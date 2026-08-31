#!/bin/bash
# Bring up postgres and the tool server, then idle.
#
#   --wait          start and idle (default)
#   --reset-db      rebuild the database from SQL, leaving the server running
#   --dump-state    write the final state to $STATE_OUT_DIR
set -euo pipefail

READY_DIR=/tmp/task-infra
SQL_DIR=/opt/sql
SERVER_DIR=/opt/tool-server
TOOL_PORT=${TOOL_PORT:-8080}
OUT_DIR=${STATE_OUT_DIR:-/out}
# pg_ctl writes here as the postgres user; the readiness marker stays in /tmp.
LOG_DIR=/var/log/task-infra

apply_sql() {
    # Filename order: schema, reference data, population, scenario.
    for file in "$SQL_DIR"/[0-9][0-9][0-9]_*.sql; do
        echo "  applying $(basename "$file")"
        su postgres -c "psql --quiet --no-psqlrc -v ON_ERROR_STOP=1 \
            -d ${POSTGRES_DB} -f $file" > /dev/null
    done
}

build_database() {
    echo "building database ${POSTGRES_DB}"
    su postgres -c "psql --quiet --no-psqlrc -v ON_ERROR_STOP=1 -d postgres -c \
        \"DROP DATABASE IF EXISTS ${POSTGRES_DB};\"" > /dev/null
    su postgres -c "psql --quiet --no-psqlrc -v ON_ERROR_STOP=1 -d postgres -c \
        \"CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};\"" > /dev/null
    apply_sql
    su postgres -c "psql --quiet --no-psqlrc -v ON_ERROR_STOP=1 -d ${POSTGRES_DB} -c \
        \"GRANT ALL ON ALL TABLES IN SCHEMA public TO ${POSTGRES_USER}; \
          GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ${POSTGRES_USER};\"" > /dev/null
}

start_postgres() {
    # --reset-db runs inside a live container, where the cluster is already up.
    if su postgres -c "pg_isready -q -h 127.0.0.1" 2>/dev/null; then
        return 0
    fi

    mkdir -p "$PGDATA"
    chown -R postgres:postgres "$PGDATA"
    chmod 0700 "$PGDATA"

    if [ ! -s "$PGDATA/PG_VERSION" ]; then
        echo "initialising cluster"
        su postgres -c "initdb --username=postgres --auth-local=trust \
            --auth-host=trust --encoding=UTF8 -D $PGDATA" > "$LOG_DIR/initdb.log" 2>&1
        # Loopback only; the tool server is the database's only client.
        echo "listen_addresses = '127.0.0.1'" >> "$PGDATA/postgresql.conf"
        echo "fsync = off" >> "$PGDATA/postgresql.conf"
        echo "host all all 127.0.0.1/32 trust" >> "$PGDATA/pg_hba.conf"
    fi

    su postgres -c "pg_ctl -D $PGDATA -l $LOG_DIR/postgres.log -w -t 60 start" \
        > /dev/null

    su postgres -c "psql --quiet --no-psqlrc -d postgres -tAc \
        \"SELECT 1 FROM pg_roles WHERE rolname='${POSTGRES_USER}'\"" \
        | grep -q 1 || su postgres -c "psql --quiet --no-psqlrc -d postgres -c \
            \"CREATE ROLE ${POSTGRES_USER} LOGIN SUPERUSER PASSWORD '${POSTGRES_PASSWORD}';\"" \
            > /dev/null
}

start_tool_server() {
    echo "starting tool server on 127.0.0.1:${TOOL_PORT}"
    ( cd "$SERVER_DIR" && exec python3 app.py --host 127.0.0.1 --port "$TOOL_PORT" ) \
        > "$LOG_DIR/tool-server.log" 2>&1 &
    echo $! > "$READY_DIR/tool-server.pid"

    for _ in $(seq 1 60); do
        if curl -sf -o /dev/null "http://127.0.0.1:${TOOL_PORT}/health"; then
            return 0
        fi
        sleep 0.5
    done
    echo "tool server failed to become healthy; log follows" >&2
    cat "$LOG_DIR/tool-server.log" >&2 || true
    return 1
}

dump_state() {
    mkdir -p "$OUT_DIR"
    local token
    token=$(cat /var/lib/task-data/admin_token)
    curl -sf -X POST -H "Authorization: Bearer ${token}" \
        "http://127.0.0.1:${TOOL_PORT}/_admin/snapshot" > /dev/null
    su postgres -c "pg_dump --data-only --column-inserts -d ${POSTGRES_DB}" \
        > "$OUT_DIR/final_state.sql"
    echo "wrote $OUT_DIR/final_state.json and $OUT_DIR/final_state.sql"
}

mkdir -p "$READY_DIR" "$LOG_DIR"
chown postgres:postgres "$LOG_DIR"
chmod 0755 "$LOG_DIR"
rm -f "$READY_DIR/.ready"

# Without this sudo prints a resolver warning over every command: the container
# hostname resolves nowhere when it has no network namespace of its own.
if ! getent hosts "$(hostname)" > /dev/null 2>&1; then
    printf '127.0.1.1\t%s\n' "$(hostname)" >> /etc/hosts 2>/dev/null || true
fi

case "${1:-}" in
    --reset-db)
        start_postgres
        build_database
        echo "database rebuilt"
        exit 0
        ;;
    --dump-state)
        dump_state
        exit 0
        ;;
esac

start_postgres
build_database
start_tool_server
touch "$READY_DIR/.ready"
echo "environment ready"

if [ "${1:-}" = "--wait" ]; then
    exec tail -f /dev/null
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi
