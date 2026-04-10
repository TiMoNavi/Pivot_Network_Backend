FROM python:3.12-alpine

WORKDIR /app

COPY benchmark_stub.py /app/benchmark_stub.py

ENV PYTHONUNBUFFERED=1
ENV BENCHMARK_KEEPALIVE_SECONDS=1800

CMD ["python", "/app/benchmark_stub.py"]
