# Backend image: FastAPI + the agent pipeline.
FROM python:3.14-slim

# Run as a non-root user (defense in depth).
RUN useradd --create-home appuser

WORKDIR /app

# Install dependencies first so Docker layer caching skips reinstalls
# when only application code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# SQLite lives on a mounted volume so data survives container restarts.
ENV DATABASE_URL=sqlite:////data/app.db
RUN mkdir /data && chown appuser /data
VOLUME /data

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
