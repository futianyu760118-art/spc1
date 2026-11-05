FROM spc-v2-backend:latest

WORKDIR /orchestrator

RUN pip install --no-cache-dir docker==7.1.0

COPY app.py .

EXPOSE 8792

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8792", "--workers", "1"]
