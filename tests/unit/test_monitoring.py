"""Unit tests for monitoring and metrics."""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta

import pytest

from src.tools.monitoring import ToolMetric, MetricsCollector, ToolLogger, measure_time


@pytest.fixture
def metric():
    """Create a sample tool metric."""
    return ToolMetric(
        tool_name="test_tool",
        status="success",
        duration_ms=100.0,
        timestamp=datetime.now(),
        error=None,
        metadata={"param": "value"},
    )


@pytest.fixture
def metrics_collector():
    """Create a metrics collector."""
    return MetricsCollector()


@pytest.fixture
def temp_log_file():
    """Create a temporary log file."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        yield f.name
        os.unlink(f.name)


def test_tool_metric_creation():
    """Test that ToolMetric is created with correct attributes."""
    timestamp = datetime.now()
    metric = ToolMetric(
        tool_name="test",
        status="success",
        duration_ms=100.0,
        timestamp=timestamp,
        error=None,
        metadata={"test": "value"},
    )

    assert metric.tool_name == "test"
    assert metric.status == "success"
    assert metric.duration_ms == 100.0
    assert metric.timestamp == timestamp
    assert metric.error is None
    assert metric.metadata == {"test": "value"}


def test_metrics_collector_record_operation(metrics_collector):
    """Test recording an operation in MetricsCollector."""
    metrics_collector.record_operation(
        tool_name="test_tool",
        status="success",
        duration_ms=100.0,
        metadata={"test": "value"},
    )

    assert len(metrics_collector.metrics) == 1
    metric = metrics_collector.metrics[0]
    assert metric.tool_name == "test_tool"
    assert metric.status == "success"
    assert metric.duration_ms == 100.0
    assert metric.metadata == {"test": "value"}


def test_metrics_collector_get_metrics_empty(metrics_collector):
    """Test getting metrics when none exist."""
    metrics = metrics_collector.get_metrics()
    assert len(metrics) == 0


def test_metrics_collector_get_metrics_filter_tool(metrics_collector):
    """Test filtering metrics by tool name."""
    metrics_collector.record_operation("tool1", "success", 100.0)
    metrics_collector.record_operation("tool2", "success", 200.0)

    metrics = metrics_collector.get_metrics(tool_name="tool1")
    assert len(metrics) == 1
    assert metrics[0]["tool_name"] == "tool1"


def test_metrics_collector_get_metrics_filter_status(metrics_collector):
    """Test filtering metrics by status."""
    metrics_collector.record_operation("tool1", "success", 100.0)
    metrics_collector.record_operation("tool2", "error", 200.0)

    metrics = metrics_collector.get_metrics(status="error")
    assert len(metrics) == 1
    assert metrics[0]["status"] == "error"


def test_metrics_collector_get_metrics_filter_since(metrics_collector):
    """Test filtering metrics by timestamp."""
    now = datetime.now()
    metrics_collector.record_operation("tool1", "success", 100.0)

    metrics = metrics_collector.get_metrics(since=now - timedelta(minutes=1))
    assert len(metrics) == 1

    metrics = metrics_collector.get_metrics(since=now + timedelta(minutes=1))
    assert len(metrics) == 0


def test_metrics_collector_get_summary_empty(metrics_collector):
    """Test getting summary when no metrics exist."""
    summary = metrics_collector.get_summary()
    assert summary["total_operations"] == 0
    assert summary["success_rate"] == 0
    assert summary["avg_duration_ms"] == 0
    assert summary["error_count"] == 0


def test_metrics_collector_get_summary(metrics_collector):
    """Test getting summary statistics."""
    metrics_collector.record_operation("tool1", "success", 100.0)
    metrics_collector.record_operation("tool1", "error", 200.0)
    metrics_collector.record_operation("tool2", "success", 300.0)

    summary = metrics_collector.get_summary()
    assert summary["total_operations"] == 3
    assert summary["success_rate"] == (2 / 3) * 100
    assert summary["avg_duration_ms"] == 200.0
    assert summary["error_count"] == 1


def test_metrics_collector_export_metrics(metrics_collector):
    """Test exporting metrics to a file."""
    metrics_collector.record_operation("tool1", "success", 100.0)

    with tempfile.NamedTemporaryFile(delete=False) as f:
        export_file = f.name
        metrics_collector.export_metrics(export_file)
        assert os.path.exists(export_file)

        with open(export_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["tool_name"] == "tool1"

        os.unlink(export_file)


def test_metrics_collector_clear(metrics_collector):
    """Test clearing all metrics."""
    metrics_collector.record_operation("tool1", "success", 100.0)
    assert len(metrics_collector.metrics) == 1

    metrics_collector.clear()
    assert len(metrics_collector.metrics) == 0


def test_tool_logger_initialization(temp_log_file):
    """Test that ToolLogger initializes correctly."""
    logger = ToolLogger(temp_log_file)
    assert isinstance(logger.logger, logging.Logger)


def test_tool_logger_log_operation(temp_log_file):
    """Test logging an operation."""
    logger = ToolLogger(temp_log_file)
    logger.log_operation(
        tool_name="test_tool", params={"param": "value"}, result={"status": "success"}
    )

    with open(temp_log_file) as f:
        log_content = f.read()
        assert "test_tool" in log_content
        assert "param" in log_content
        assert "success" in log_content


def test_tool_logger_log_error(temp_log_file):
    """Test logging an error."""
    logger = ToolLogger(temp_log_file)
    logger.log_error(
        tool_name="test_tool", error="Test error", context={"additional": "info"}
    )

    with open(temp_log_file) as f:
        log_content = f.read()
        assert "test_tool" in log_content
        assert "Test error" in log_content
        assert "additional" in log_content


@pytest.mark.parametrize("should_raise", [False, True])
def test_measure_time_decorator(should_raise):
    """Test the measure_time decorator."""

    @measure_time
    def test_function():
        if should_raise:
            raise ValueError("Test error")
        return "success"

    if should_raise:
        with pytest.raises(ValueError):
            result, duration = test_function()
    else:
        result, duration = test_function()
        assert result == "success"
        assert isinstance(duration, float)
        assert duration >= 0
