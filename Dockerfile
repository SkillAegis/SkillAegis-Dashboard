FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && apt-get purge -y --auto-remove \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools && pip install -r backend/requirements.txt

WORKDIR /app/backend
RUN cp config.py.sample config.py

WORKDIR /app
EXPOSE 4001

CMD ["./start.sh"]
