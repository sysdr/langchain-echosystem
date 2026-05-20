FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/
COPY backend/app backend/app
COPY backend/scripts backend/scripts
COPY agent /app/agent
COPY backend/agent.py backend/agent.py

RUN pip install --no-cache-dir ./backend

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
