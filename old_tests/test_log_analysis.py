"""Tests for log analysis functionality."""
import pytest
from pathlib import Path
import json
from datetime import datetime, timedelta
from src.log_analysis import LogAnalyzer

@pytest.fixture
def sample_logs(tmp_path):
    """Create sample log files for testing."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    
    # Create sample log files with different timestamps
    timestamps = [
        datetime.now() - timedelta(hours=2),
        datetime.now() - timedelta(hours=1),
        datetime.now()
    ]
    
    log_files = []
    for i, ts in enumerate(timestamps):
        log_file = log_dir / f"prompt_log_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jsonl"
        log_files.append(log_file)
        
        # Write sample log entries
        entries = [
            {
                "timestamp": (ts + timedelta(minutes=m)).isoformat(),
                "prompt": f"Test prompt {m}",
                "response_summary": "Success" if m % 2 == 0 else "Error: Rate limit exceeded",
                "tools_used": [{"tool": f"tool_{m}"}]
            }
            for m in range(3)
        ]
        
        with open(log_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
    
    return log_dir

def test_log_file_discovery(sample_logs):
    """Test that analyzer can find and load log files."""
    analyzer = LogAnalyzer(sample_logs)
    assert len(analyzer.log_files) == 3
    assert all(f.suffix == ".jsonl" for f in analyzer.log_files)

def test_query_logs(sample_logs):
    """Test querying log contents with filters."""
    analyzer = LogAnalyzer(sample_logs)
    
    # Query by time range
    start_time = datetime.now() - timedelta(hours=1)
    results = analyzer.query_logs(start_time=start_time)
    
    # Debug information
    print("\nDebug information:")
    print(f"Start time: {start_time}")
    print("\nAll log files:")
    for log_file in sorted(analyzer.log_files):
        with open(log_file) as f:
            entries = [json.loads(line) for line in f]
            print(f"\nFile: {log_file.name}")
            for entry in entries:
                ts = datetime.fromisoformat(entry["timestamp"])
                print(f"  {ts}, {entry['prompt']}")
                if start_time:
                    print(f"    Comparison: {ts} {'>==' if ts == start_time else '>>' if ts > start_time else '<<'} {start_time}")
    
    print("\nResults:")
    for entry in sorted(results, key=lambda x: x["timestamp"]):
        print(f"Timestamp: {entry['timestamp']}, Prompt: {entry['prompt']}")
    
    assert len(results) == 6  # 2 files * 3 entries
    
    # Query by error status
    error_results = analyzer.query_logs(contains_error=True)
    assert len(error_results) == 3  # Every other entry is an error
    
    # Query by tool usage
    tool_results = analyzer.query_logs(tool_name="tool_1")
    assert len(tool_results) == 3  # One tool_1 entry per file

def test_generate_statistics(sample_logs):
    """Test generating usage statistics."""
    analyzer = LogAnalyzer(sample_logs)
    stats = analyzer.generate_statistics()
    
    assert "total_requests" in stats
    assert stats["total_requests"] == 9  # 3 files * 3 entries
    assert "requests_per_hour" in stats
    assert "most_used_tools" in stats
    assert len(stats["most_used_tools"]) > 0

def test_error_rate_tracking(sample_logs):
    """Test tracking error rates over time."""
    analyzer = LogAnalyzer(sample_logs)
    error_rates = analyzer.track_error_rates()
    
    assert "overall_error_rate" in error_rates
    assert error_rates["overall_error_rate"] == pytest.approx(0.333, rel=0.01)  # 1/3 of entries are errors
    assert "error_rate_by_hour" in error_rates
    assert len(error_rates["error_rate_by_hour"]) > 0

def test_invalid_log_dir():
    """Test handling of invalid log directory."""
    with pytest.raises(ValueError):
        LogAnalyzer(Path("/nonexistent/path"))

def test_corrupted_log_file(sample_logs):
    """Test handling of corrupted log files."""
    # Create a corrupted log file
    corrupt_file = sample_logs / "prompt_log_corrupted.jsonl"
    with open(corrupt_file, "w") as f:
        f.write("This is not valid JSON\n")
        f.write(json.dumps({"timestamp": datetime.now().isoformat()}) + "\n")
    
    analyzer = LogAnalyzer(sample_logs)
    results = analyzer.query_logs()  # Should skip corrupted entries
    assert len(results) == 9  # Only valid entries from original files 