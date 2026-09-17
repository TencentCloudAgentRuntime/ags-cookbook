FROM python:3.12-alpine

COPY workspace_server.py /opt/hands/workspace_server.py

RUN mkdir -p /workspace \
    && adduser -D -u 10001 hands \
    && chown -R hands:hands /workspace /opt/hands

USER hands
WORKDIR /workspace
ENV PORT=8080 \
    WORKSPACE_DIR=/workspace

EXPOSE 8080

ENTRYPOINT ["python3", "/opt/hands/workspace_server.py"]
