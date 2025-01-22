"""
Log analysis tools for Anthropic client logs.
"""
from typing import Dict, List, Optional, Union
from pathlib import Path
import json
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict

class LogAnalyzer:
    """Analyzer for Anthropic client log files."""
    
    def __init__(self, log_dir: Union[str, Path] = "logs"):
        """Initialize the log analyzer.
        
        Args:
            log_dir: Directory containing log files
        """
        self.log_dir = Path(log_dir)
        if not self.log_dir.exists():
            raise ValueError(f"Log directory {log_dir} does not exist")
    
    def get_log_files(self, start_date: Optional[datetime] = None, 
                      end_date: Optional[datetime] = None) -> List[Path]:
        """Get list of log files in the specified date range.
        
        Args:
            start_date: Start date for log files (inclusive)
            end_date: End date for log files (inclusive)
            
        Returns:
            List of log file paths
        """
        log_files = sorted(self.log_dir.glob("prompt_log_*.jsonl"))
        
        if not start_date and not end_date:
            return log_files
            
        filtered_files = []
        for file in log_files:
            # Extract date from filename (format: prompt_log_YYYYMMDD_HHMMSS_microseconds.jsonl)
            try:
                date_str = file.stem.split('_')[2]
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                if start_date and file_date < start_date:
                    continue
                if end_date and file_date > end_date:
                    continue
                    
                filtered_files.append(file)
            except (IndexError, ValueError):
                continue
                
        return filtered_files
    
    def read_logs(self, files: List[Path]) -> pd.DataFrame:
        """Read and parse log files into a DataFrame.
        
        Args:
            files: List of log files to read
            
        Returns:
            DataFrame containing parsed log entries
        """
        records = []
        for file in files:
            with file.open() as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        record['timestamp'] = pd.to_datetime(record['timestamp'])
                        records.append(record)
                    except (json.JSONDecodeError, KeyError):
                        continue
        
        return pd.DataFrame.from_records(records)
    
    def get_usage_stats(self, start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None) -> Dict:
        """Generate usage statistics for the specified period.
        
        Args:
            start_date: Start date for analysis (inclusive)
            end_date: End date for analysis (inclusive)
            
        Returns:
            Dictionary containing usage statistics
        """
        files = self.get_log_files(start_date, end_date)
        df = self.read_logs(files)
        
        if df.empty:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "error_rate": 0,
                "avg_tokens_per_request": 0
            }
        
        # Calculate basic stats
        total_requests = len(df)
        total_tokens = df['token_usage'].sum()
        error_count = df['response_summary'].str.startswith('Error:').sum()
        
        stats = {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "error_rate": error_count / total_requests if total_requests > 0 else 0,
            "avg_tokens_per_request": total_tokens / total_requests if total_requests > 0 else 0
        }
        
        return stats
    
    def query_logs(self, query: Dict[str, str], 
                  start_date: Optional[datetime] = None,
                  end_date: Optional[datetime] = None) -> pd.DataFrame:
        """Query log contents with filters.
        
        Args:
            query: Dictionary of field:value pairs to filter by
            start_date: Start date for query (inclusive)
            end_date: End date for query (inclusive)
            
        Returns:
            DataFrame containing matching log entries
        """
        files = self.get_log_files(start_date, end_date)
        df = self.read_logs(files)
        
        if df.empty:
            return df
            
        # Apply filters
        for field, value in query.items():
            if field in df.columns:
                df = df[df[field].astype(str).str.contains(value, case=False)]
        
        return df
    
    def get_error_summary(self, start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> Dict:
        """Generate summary of errors in the specified period.
        
        Args:
            start_date: Start date for analysis (inclusive)
            end_date: End date for analysis (inclusive)
            
        Returns:
            Dictionary containing error statistics
        """
        files = self.get_log_files(start_date, end_date)
        df = self.read_logs(files)
        
        if df.empty:
            return {
                "total_errors": 0,
                "error_types": {},
                "error_rate": 0
            }
        
        # Get error entries
        error_df = df[df['response_summary'].str.startswith('Error:', na=False)]
        
        # Count error types
        error_types = defaultdict(int)
        for error in error_df['response_summary']:
            error_type = error.split(':', 1)[1].strip()
            error_types[error_type] += 1
        
        summary = {
            "total_errors": len(error_df),
            "error_types": dict(error_types),
            "error_rate": len(error_df) / len(df)
        }
        
        return summary 