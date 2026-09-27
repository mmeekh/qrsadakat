FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHEABBY_HOST=0.0.0.0 \
    CHEABBY_PORT=8088 \
    CHEABBY_DB=/data/pilot.sqlite3

WORKDIR /app
COPY cheabby/ /app/cheabby/
COPY static/ /app/static/
RUN mkdir /data && chown 10002:10002 /data
USER 10002:10002
EXPOSE 8088
CMD ["python", "-m", "cheabby"]
