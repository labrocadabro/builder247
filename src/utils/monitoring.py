"""Monitoring and metrics for tool operations."""

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class ToolMetric:
    """Metric for a single tool operation."""

    tool_name: str
    status: str
    duration_ms: float
    timestamp: datetime
    error: Optional[str] = None
    metadata: Optional[Dict] = None


class MetricsCollector:
    """Collects and manages tool metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self.metrics: List[ToolMetric] = []
        self.logger = logging.getLogger(__name__)

    def record_operation(
        self,
        tool_name: str,
        status: str,
        duration_ms: float,
        error: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record a tool operation.

        Args:
            tool_name: Name of the tool
            status: Operation status (success/error)
            duration_ms: Operation duration in milliseconds
            error: Optional error message
            metadata: Optional operation metadata
        """
        metric = ToolMetric(
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms,
            timestamp=datetime.now(),
            error=error,
            metadata=metadata,
        )
        self.metrics.append(metric)
        self.logger.info(f"Recorded metric for {tool_name}: {status}")

    def get_metrics(
        self,
        tool_name: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get filtered metrics.

        Args:
            tool_name: Filter by tool name
            status: Filter by status
            since: Filter by timestamp

        Returns:
            List of metric dictionaries
        """
        filtered = self.metrics

        if tool_name:
            filtered = [m for m in filtered if m.tool_name == tool_name]

        if status:
            filtered = [m for m in filtered if m.status == status]

        if since:
            filtered = [m for m in filtered if m.timestamp >= since]

        return [asdict(m) for m in filtered]

    def get_summary(
        self,
        tool_name: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict:
        """Get summary statistics.

        Args:
            tool_name: Filter by tool name
            since: Filter by timestamp

        Returns:
            Summary statistics dictionary
        """
        metrics = self.get_metrics(tool_name=tool_name, since=since)

        if not metrics:
            return {
                "total_operations": 0,
                "success_rate": 0,
                "avg_duration_ms": 0,
                "error_count": 0,
            }

        total = len(metrics)
        successes = sum(1 for m in metrics if m["status"] == "success")
        errors = sum(1 for m in metrics if m["status"] == "error")
        durations = [m["duration_ms"] for m in metrics]

        return {
            "total_operations": total,
            "success_rate": (successes / total) * 100,
            "avg_duration_ms": sum(durations) / total,
            "error_count": errors,
        }

    def export_metrics(self, file_path: str) -> None:
        """Export metrics to JSON file.

        Args:
            file_path: Path to export file
        """
        try:
            metrics_data = [asdict(m) for m in self.metrics]
            with open(file_path, "w") as f:
                json.dump(metrics_data, f, indent=2, default=str)
            self.logger.info(f"Exported metrics to {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to export metrics: {e}")

    def clear(self) -> None:
        """Clear all collected metrics."""
        self.metrics.clear()
        self.logger.info("Cleared all metrics")


class ToolLogger:
    """Enhanced logging for tool operations."""

    def __init__(self, log_file: Optional[str] = None):
        """Initialize tool logger.

        Args:
            log_file: Optional log file path
        """
        self.logger = logging.getLogger(__name__)

        if log_file:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            self.logger.addHandler(handler)

    def log_operation(
        self,
        tool_name: str,
        params: Dict,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log a tool operation.

        Args:
            tool_name: Name of the tool
            params: Operation parameters
            result: Optional operation result
            error: Optional error message
        """
        log_data = {
            "tool": tool_name,
            "params": params,
            "timestamp": datetime.now().isoformat(),
        }

        if result:
            log_data["result"] = result

        if error:
            log_data["error"] = error

        self.logger.info(json.dumps(log_data))

    def log_error(
        self, tool_name: str, error: str, context: Optional[Dict] = None
    ) -> None:
        """Log a tool error.

        Args:
            tool_name: Name of the tool
            error: Error message
            context: Optional error context
        """
        log_data = {
            "tool": tool_name,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }

        if context:
            log_data["context"] = context

        self.logger.error(json.dumps(log_data))


def measure_time(func):
    """Decorator to measure function execution time.

    Args:
        func: Function to measure

    Returns:
        Wrapped function that measures execution time
    """

    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            duration = (time.time() - start) * 1000
            return result, duration
        except Exception as e:
            duration = (time.time() - start) * 1000
            raise e

    return wrapper
