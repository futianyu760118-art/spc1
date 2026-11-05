FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SANDBOX_WORK_ROOT=/work

RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm bash && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -u 10001 -m sandbox && \
    mkdir -p /run/sandbox /work && \
    chown -R sandbox:sandbox /run/sandbox /work

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py task_runner.py ./

USER sandbox

EXPOSE 8791

CMD ["uvicorn", "app:app", "--uds", "/run/sandbox/sandbox.sock", "--workers", "1"]
