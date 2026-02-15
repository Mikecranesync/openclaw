"""In-process metrics collector — no external deps."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class MetricsCollector:
    request_count: int = 0
    intent_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    provider_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latencies: list[int] = field(default_factory=list)
    _start_time: float = field(default_factory=time.time)

    def record_request(self, intent: str, provider: str = "", latency_ms: int = 0) -> None:
        self.request_count += 1
        self.intent_counts[intent] += 1
        if provider:
            self.provider_counts[provider] += 1
        if latency_ms:
            self.latencies.append(latency_ms)
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-500:]

    def summary(self) -> dict:
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        return {
            "uptime_seconds": int(time.time() - self._start_time),
            "total_requests": self.request_count,
            "intents": dict(self.intent_counts),
            "providers": dict(self.provider_counts),
            "avg_latency_ms": int(avg_latency),
        }
