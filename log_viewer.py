#!/usr/bin/env python3
"""
Log Viewer for Gmail API Service
View, search, and manage application logs
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import argparse

def view_logs(log_file="logs/gmail_api.log", lines=50, search=None, level=None):
    """View the last N lines of the log file with optional filtering"""

    log_path = Path(log_file)
    if not log_path.exists():
        print(f"❌ Log file not found: {log_file}")
        return

    print(f"📄 Viewing log file: {log_file}")
    print(f"Showing last {lines} lines")
    if search:
        print(f"🔍 Filtering by: {search}")
    if level:
        print(f"📈 Filtering by level: {level}")
    print("-" * 80)

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        # Filter lines
        filtered_lines = []
        for line in all_lines:
            if search and search.lower() not in line.lower():
                continue
            if level and f'- {level.upper()} -' not in line:
                continue
            filtered_lines.append(line)

        # Show last N lines
        lines_to_show = filtered_lines[-lines:] if filtered_lines else []

        if not lines_to_show:
            print("📭 No matching log entries found")
            return

        for line in lines_to_show:
            print(line.rstrip())

        print("-" * 80)
        print(f"Total matching entries: {len(filtered_lines)}")

    except Exception as e:
        print(f"❌ Error reading log file: {e}")

def clear_logs(log_file="logs/gmail_api.log", confirm=True):
    """Clear the log file"""

    log_path = Path(log_file)
    if not log_path.exists():
        print(f"❌ Log file not found: {log_file}")
        return

    if confirm:
        size = log_path.stat().st_size / 1024 / 1024  # Size in MB
        response = input(f"Are you sure you want to clear the log file ({size:.2f} MB)? This will create a backup. (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("❌ Operation cancelled")
            return

    try:
        # Create backup
        backup_name = f"{log_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        log_path.rename(backup_name)
        print(f"💾 Backup created: {backup_name}")

        # Create new empty log file
        log_path.touch()
        print(f"🗑️ Log file cleared: {log_file}")

    except Exception as e:
        print(f"❌ Error clearing log file: {e}")

def log_stats(log_file="logs/gmail_api.log"):
    """Show statistics about the log file"""

    log_path = Path(log_file)
    if not log_path.exists():
        print(f"❌ Log file not found: {log_file}")
        return

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Basic stats
        total_lines = len(lines)
        size_mb = log_path.stat().st_size / 1024 / 1024

        # Level counts
        levels = {'DEBUG': 0, 'INFO': 0, 'WARNING': 0, 'ERROR': 0, 'CRITICAL': 0}
        for line in lines:
            for level in levels:
                if f'- {level} -' in line:
                    levels[level] += 1

        print(f"Log File Statistics: {log_file}")
        print("-" * 40)
        print(f"📏 File size: {size_mb:.2f} MB")
        print(f"📝 Total entries: {total_lines}")
        print()
        print("📈 Entries by level:")
        for level, count in levels.items():
            if count > 0:
                print(f"  {level}: {count}")
        print()

        # Recent activity
        if lines:
            print("🕐 Recent activity:")
            recent_lines = lines[-5:]  # Last 5 entries
            for line in recent_lines:
                timestamp = line.split(' - ')[0] if ' - ' in line else 'Unknown'
                level = 'UNKNOWN'
                for lvl in levels:
                    if f'- {lvl} -' in line:
                        level = lvl
                        break
                message = line.split(' - ', 2)[-1].strip() if ' - ' in line else line.strip()
                print(f"  [{timestamp}] {level}: {message[:60]}{'...' if len(message) > 60 else ''}")

    except Exception as e:
        print(f"❌ Error analyzing log file: {e}")

def main():
    parser = argparse.ArgumentParser(description="Gmail API Log Viewer")
    parser.add_argument('--file', '-f', default='logs/gmail_api.log',
                       help='Log file to view (default: logs/gmail_api.log)')
    parser.add_argument('--lines', '-n', type=int, default=50,
                       help='Number of lines to show (default: 50)')
    parser.add_argument('--search', '-s',
                       help='Search for specific text in logs')
    parser.add_argument('--level', '-l', choices=['debug', 'info', 'warning', 'error', 'critical'],
                       help='Filter by log level')
    parser.add_argument('--stats', action='store_true',
                       help='Show log file statistics')
    parser.add_argument('--clear', action='store_true',
                       help='Clear the log file (creates backup)')

    args = parser.parse_args()

    if args.clear:
        clear_logs(args.file)
    elif args.stats:
        log_stats(args.file)
    else:
        view_logs(args.file, args.lines, args.search, args.level)

if __name__ == "__main__":
    main()
