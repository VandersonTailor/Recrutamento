from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest


COMM_DISPATCH_TOTAL = Counter(
    "comm_dispatch_total",
    "Total de eventos processados no dispatch de comunicação",
    ["status", "channel"],
)
COMM_DISPATCH_LATENCY = Histogram(
    "comm_dispatch_latency_seconds",
    "Latência de envio por canal",
    ["channel"],
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20),
)
COMM_BACKLOG = Gauge("comm_backlog_total", "Total de mensagens pendentes/retrying")
OCR_QUEUE_BACKLOG = Gauge("ocr_queue_backlog_total", "Total de itens pendentes na fila OCR/NLP")
DLQ_BACKLOG = Gauge("dead_letter_backlog_total", "Total de eventos em dead letter queue com status open")


def render_metrics() -> bytes:
    return generate_latest()
