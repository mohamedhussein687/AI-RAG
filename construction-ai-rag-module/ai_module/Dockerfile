FROM python:3.11.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --system --home /app --shell /usr/sbin/nologin aiapp
COPY pyproject.toml alembic.ini ./
RUN pip install --no-cache-dir .
COPY --chown=aiapp:aiapp app ./app
COPY --chown=aiapp:aiapp ingestion_worker ./ingestion_worker
COPY --chown=aiapp:aiapp config ./config
RUN chmod -R u=rwX,go=rX /app/app /app/ingestion_worker /app/config
USER aiapp
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
