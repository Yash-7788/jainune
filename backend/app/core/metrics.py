"""
Zero-dependency, thread-safe Prometheus metrics collector and text exposition generator.
Complies with Prometheus text exposition format version 0.0.4.
"""
import threading
import time
from collections import defaultdict
from typing import Dict, List, Tuple


class PrometheusRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        # {(method, endpoint, status): count}
        self.request_counts: Dict[Tuple[str, str, str], int] = defaultdict(int)
        # in-flight requests
        self.in_progress: int = 0
        # {(method, endpoint): {bucket: count}}
        self.buckets: List[float] = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self.duration_buckets: Dict[Tuple[str, str], Dict[float, int]] = defaultdict(lambda: defaultdict(int))
        self.duration_sums: Dict[Tuple[str, str], float] = defaultdict(float)
        self.duration_counts: Dict[Tuple[str, str], int] = defaultdict(int)

    def record_request_start(self):
        with self._lock:
            self.in_progress += 1

    def record_request_end(self, method: str, endpoint: str, status: int, duration_seconds: float):
        status_str = str(status)
        with self._lock:
            self.in_progress = max(0, self.in_progress - 1)
            self.request_counts[(method, endpoint, status_str)] += 1
            
            key = (method, endpoint)
            self.duration_sums[key] += duration_seconds
            self.duration_counts[key] += 1
            for b in self.buckets:
                if duration_seconds <= b:
                    self.duration_buckets[key][b] += 1

    def generate_prometheus_output(self, version: str = "1.0.0", environment: str = "development") -> str:
        lines: List[str] = []
        with self._lock:
            # 1. Build Info Gauge
            lines.append("# HELP app_build_info Application build information.")
            lines.append("# TYPE app_build_info gauge")
            lines.append(f'app_build_info{{environment="{environment}",version="{version}"}} 1')

            # 2. In-flight requests gauge
            lines.append("# HELP http_requests_in_progress Current number of HTTP requests being processed.")
            lines.append("# TYPE http_requests_in_progress gauge")
            lines.append(f"http_requests_in_progress {self.in_progress}")

            # 3. HTTP Request Counts Counter
            lines.append("# HELP http_requests_total Total number of HTTP requests processed.")
            lines.append("# TYPE http_requests_total counter")
            for (method, endpoint, status), count in sorted(self.request_counts.items()):
                lines.append(f'http_requests_total{{endpoint="{endpoint}",method="{method}",status="{status}"}} {count}')

            # 4. Request Duration Histogram
            lines.append("# HELP http_request_duration_seconds HTTP request duration in seconds.")
            lines.append("# TYPE http_request_duration_seconds histogram")
            for (method, endpoint), total_count in sorted(self.duration_counts.items()):
                for b in self.buckets:
                    count_in_bucket = self.duration_buckets[(method, endpoint)][b]
                    lines.append(
                        f'http_request_duration_seconds_bucket{{endpoint="{endpoint}",le="{b}",method="{method}"}} {count_in_bucket}'
                    )
                lines.append(
                    f'http_request_duration_seconds_bucket{{endpoint="{endpoint}",le="+Inf",method="{method}"}} {total_count}'
                )
                dur_sum = self.duration_sums[(method, endpoint)]
                lines.append(f'http_request_duration_seconds_sum{{endpoint="{endpoint}",method="{method}"}} {dur_sum:.6f}')
                lines.append(f'http_request_duration_seconds_count{{endpoint="{endpoint}",method="{method}"}} {total_count}')

        return "\n".join(lines) + "\n"


metrics_registry = PrometheusRegistry()
