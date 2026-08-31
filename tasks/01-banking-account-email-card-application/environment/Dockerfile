# Voice-agent environment: postgres plus the tool server that fronts it.
# The database is built at container start by task-init.sh, not baked into the
# image, so a run can be reset without a rebuild.
FROM postgres:16-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl jq procps python3 python3-psycopg2 ripgrep \
        sudo tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Etc/UTC \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN useradd --create-home --shell /bin/bash agent

RUN install -d -m 0755 -o root -g root /opt/tool-server
COPY --chown=root:root --chmod=0444 server/ /opt/tool-server/
RUN chmod 0555 /opt/tool-server

RUN install -d -m 0755 -o root -g root /opt/sql
COPY --chown=root:root --chmod=0444 sql/ /opt/sql/

# Root-only: the agent account must not be able to read the expected end state.
RUN install -d -m 0700 -o root -g root /var/lib/task-data /var/lib/task-data/verifier
COPY --chown=root:root --chmod=600 verifier-data/ /var/lib/task-data/verifier/

# Readable, not writable: a run cannot edit the policy it is held to.
RUN install -d -m 0755 -o agent -g agent /workspace
COPY --chown=root:root --chmod=0444 workspace/ /workspace/

# Where the run records what it said to the caller.
RUN install -m 0666 -o agent -g agent /dev/null /workspace/transcript.txt

# Mount a host directory here to keep a run's final state.
RUN install -d -m 0777 -o root -g root /out
VOLUME ["/out"]

COPY --chown=root:root task-init.sh /usr/local/bin/task-init.sh
RUN chmod 0755 /usr/local/bin/task-init.sh

# PGDATA outside the image: the cluster is created on boot and can be mounted.
ENV PGDATA=/var/lib/postgresql/data \
    POSTGRES_DB=voiceenv \
    POSTGRES_USER=voiceenv \
    POSTGRES_PASSWORD=voiceenv \
    TOOL_DB_DSN="host=127.0.0.1 port=5432 dbname=voiceenv user=voiceenv password=voiceenv" \
    TOOL_SERVER_URL=http://127.0.0.1:8080 \
    STATE_OUT_DIR=/out

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/task-init.sh"]
CMD ["--wait"]
