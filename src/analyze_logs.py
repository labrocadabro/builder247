#!/usr/bin/env python3
"""
Command-line interface for analyzing Anthropic client logs.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
from log_analyzer import LogAnalyzer

def parse_date(date_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str, "%Y-%m-%d")

def main():
    parser = argparse.ArgumentParser(description="Analyze Anthropic client logs")
    parser.add_argument("--log-dir", type=str, default="logs",
                       help="Directory containing log files")
    parser.add_argument("--start-date", type=str,
                       help="Start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", type=str,
                       help="End date in YYYY-MM-DD format")
    
    subparsers = parser.add_subparsers(dest="command", help="Analysis command")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", 
                                        help="Get usage statistics")
    
    # Query command
    query_parser = subparsers.add_parser("query",
                                        help="Query log contents")
    query_parser.add_argument("--field", type=str, required=True,
                            help="Field to query")
    query_parser.add_argument("--value", type=str, required=True,
                            help="Value to search for")
    query_parser.add_argument("--output", type=str,
                            help="Output file for results (CSV format)")
    
    # Errors command
    errors_parser = subparsers.add_parser("errors",
                                         help="Get error summary")
    
    args = parser.parse_args()
    
    # Parse dates if provided
    start_date = parse_date(args.start_date) if args.start_date else None
    end_date = parse_date(args.end_date) if args.end_date else None
    
    # Initialize analyzer
    analyzer = LogAnalyzer(args.log_dir)
    
    try:
        if args.command == "stats":
            stats = analyzer.get_usage_stats(start_date, end_date)
            print(json.dumps(stats, indent=2))
            
        elif args.command == "query":
            query = {args.field: args.value}
            results = analyzer.query_logs(query, start_date, end_date)
            
            if args.output:
                results.to_csv(args.output, index=False)
                print(f"Results saved to {args.output}")
            else:
                print(results.to_string())
                
        elif args.command == "errors":
            summary = analyzer.get_error_summary(start_date, end_date)
            print(json.dumps(summary, indent=2))
            
        else:
            parser.print_help()
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
        
    return 0

if __name__ == "__main__":
    exit(main()) 