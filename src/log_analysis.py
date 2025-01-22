"""Log analysis tools for analyzing Claude API interactions."""
from pathlib import Path
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict

class LogAnalyzer:
    """Analyzer for Claude API interaction logs."""
    
    def __init__(self, log_dir: Path):
        """Initialize the log analyzer.
        
        Args:
            log_dir: Path to directory containing log files
        
        Raises:
            ValueError: If log directory doesn't exist
        """
        if not log_dir.exists():
            raise ValueError(f"Log directory does not exist: {log_dir}")
            
        self.log_dir = log_dir
        self.log_files = sorted(log_dir.glob("prompt_log_*.jsonl"))
    
    def _parse_log_entry(self, line: str) -> Optional[Dict]:
        """Parse a single log entry, returning None if invalid.
        
        Args:
            line: Raw log line to parse
            
        Returns:
            Parsed log entry as dict, or None if invalid
        """
        try:
            entry = json.loads(line)
            # Validate required fields
            required_fields = ["timestamp", "prompt", "response_summary", "tools_used"]
            if not all(field in entry for field in required_fields):
                return None
            entry["timestamp"] = datetime.fromisoformat(entry["timestamp"])
            return entry
        except (json.JSONDecodeError, ValueError, KeyError):
            return None
    
    def query_logs(self, 
                  start_time: Optional[datetime] = None,
                  end_time: Optional[datetime] = None,
                  contains_error: Optional[bool] = None,
                  tool_name: Optional[str] = None) -> List[Dict]:
        """Query log contents with optional filters.
        
        Args:
            start_time: Optional start time filter (inclusive)
            end_time: Optional end time filter (inclusive)
            contains_error: Filter for entries containing errors
            tool_name: Filter for entries using specific tool
            
        Returns:
            List of matching log entries
        """
        results = []
        
        # Sort log files by timestamp to process them in order
        sorted_files = sorted(self.log_files)
        
        # Truncate start and end times to second precision
        if start_time:
            start_time = start_time.replace(microsecond=0)
        if end_time:
            end_time = end_time.replace(microsecond=0)
        
        for log_file in sorted_files:
            with open(log_file) as f:
                for line in f:
                    entry = self._parse_log_entry(line)
                    if not entry:
                        continue
                        
                    # Apply filters with inclusive comparison for both start and end time
                    entry_time = entry["timestamp"].replace(microsecond=0)
                    if start_time and entry_time < start_time:
                        continue
                    if end_time and entry_time > end_time:
                        continue
                    
                    if contains_error is not None:
                        has_error = "Error:" in entry["response_summary"]
                        if has_error != contains_error:
                            continue
                        
                    if tool_name:
                        tools = [t["tool"] for t in entry["tools_used"]]
                        if tool_name not in tools:
                            continue
                    
                    results.append(entry)
        
        return sorted(results, key=lambda x: x["timestamp"])
    
    def generate_statistics(self) -> Dict[str, Any]:
        """Generate usage statistics from logs.
        
        Returns:
            Dictionary containing various statistics
        """
        entries = self.query_logs()
        if not entries:
            return {
                "total_requests": 0,
                "requests_per_hour": {},
                "most_used_tools": []
            }
        
        # Calculate requests per hour
        hours = defaultdict(int)
        tools = Counter()
        
        for entry in entries:
            hour = entry["timestamp"].replace(minute=0, second=0, microsecond=0)
            hours[hour] += 1
            
            for tool in entry["tools_used"]:
                tools[tool["tool"]] += 1
        
        return {
            "total_requests": len(entries),
            "requests_per_hour": dict(hours),
            "most_used_tools": tools.most_common(10)
        }
    
    def track_error_rates(self) -> Dict[str, Any]:
        """Track error rates over time.
        
        Returns:
            Dictionary containing error rate statistics
        """
        entries = self.query_logs()
        if not entries:
            return {
                "overall_error_rate": 0.0,
                "error_rate_by_hour": {}
            }
        
        # Track errors by hour
        hours = defaultdict(lambda: {"total": 0, "errors": 0})
        total_errors = 0
        
        for entry in entries:
            hour = entry["timestamp"].replace(minute=0, second=0, microsecond=0)
            hours[hour]["total"] += 1
            
            if "Error:" in entry["response_summary"]:
                hours[hour]["errors"] += 1
                total_errors += 1
        
        # Calculate error rates
        error_rates = {
            str(hour): stats["errors"] / stats["total"]
            for hour, stats in hours.items()
        }
        
        return {
            "overall_error_rate": total_errors / len(entries),
            "error_rate_by_hour": error_rates
        } 