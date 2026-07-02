import os
import re
import json
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Combined Log Format Regex
LOG_REGEX = re.compile(
    r'^(\S+) \S+ \S+ \[([^\]]+)\] "([^"]+)" (\d{3}) (\d+|-) "([^"]*)" "([^"]*)"'
)

def parse_log_file(filepath):
    if not os.path.exists(filepath):
        console.print(f"[red]Error: Log file '{filepath}' does not exist.[/red]")
        return None
        
    parsed_entries = []
    malformed_count = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            match = LOG_REGEX.match(line)
            if not match:
                malformed_count += 1
                continue
                
            ip, timestamp, request_line, status, bytes_sent, referrer, user_agent = match.groups()
            
            # Parse request line: METHOD PATH VERSION
            request_parts = request_line.split()
            if len(request_parts) >= 2:
                method = request_parts[0]
                full_path = request_parts[1]
                # Strip query parameters (e.g. /checkout?id=12 -> /checkout)
                endpoint = full_path.split('?')[0]
            else:
                method = "UNKNOWN"
                endpoint = "UNKNOWN"
                
            # Handle '-' for bytes_sent
            bytes_val = 0 if bytes_sent == "-" else int(bytes_sent)
            
            parsed_entries.append({
                "ip": ip,
                "timestamp": timestamp,
                "method": method,
                "endpoint": endpoint,
                "status": int(status),
                "bytes": bytes_val,
                "referrer": referrer,
                "user_agent": user_agent
            })
            
    if malformed_count > 0:
        console.print(f"[yellow]Warning: Skipped {malformed_count} malformed log entries.[/yellow]")
        
    return parsed_entries

def analyze_logs(entries):
    if not entries:
        return {}
        
    total_requests = len(entries)
    total_bytes = sum(entry['bytes'] for entry in entries)
    
    # Counters
    status_counts = Counter(entry['status'] for entry in entries)
    endpoint_counts = Counter(entry['endpoint'] for entry in entries)
    ip_counts = Counter(entry['ip'] for entry in entries)
    
    # List of 4xx and 5xx errors (limit details to avoid massive report files)
    errors = []
    for entry in entries:
        if entry['status'] >= 400:
            errors.append({
                "status": entry['status'],
                "method": entry['method'],
                "endpoint": entry['endpoint'],
                "ip": entry['ip'],
                "timestamp": entry['timestamp']
            })
            
    # Compile report structure
    report = {
        "summary": {
            "total_requests": total_requests,
            "total_bandwidth_mb": round(total_bytes / (1024 * 1024), 2),
            "malformed_entries_skipped": 0
        },
        "status_code_counts": dict(status_counts),
        "top_endpoints": endpoint_counts.most_common(5),
        "top_ips": ip_counts.most_common(5),
        "errors_count": len(errors),
        "recent_errors": errors[:15]  # Limit saved errors in JSON for readability
    }
    
    return report

def save_report(report, filepath="report.json"):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=4)
        console.print(f"[green]Analysis report saved to '{filepath}'[/green]")
    except Exception as e:
        console.print(f"[red]Error saving JSON report: {e}[/red]")

def display_console_report(report):
    if not report:
        console.print("[red]No data analyzed to display report.[/red]")
        return
        
    summary = report['summary']
    
    # Summary Info
    summary_text = (
        f"Total Requests: {summary['total_requests']}\n"
        f"Total Bandwidth: {summary['total_bandwidth_mb']} MB"
    )
    console.print(Panel(summary_text, title="Summary Statistics", border_style="cyan"))
    
    # Status Codes Table
    status_table = Table(title="HTTP Status Codes Distribution")
    status_table.add_column("Status Code", style="bold yellow")
    status_table.add_column("Count", style="green")
    for code, count in sorted(report['status_code_counts'].items()):
        status_table.add_row(str(code), str(count))
    console.print(status_table)
    
    # Top Endpoints Table
    endpoint_table = Table(title="Top 5 Endpoints (Clean Paths)")
    endpoint_table.add_column("Endpoint", style="bold blue")
    endpoint_table.add_column("Requests", style="green")
    for endpoint, count in report['top_endpoints']:
        endpoint_table.add_row(endpoint, str(count))
    console.print(endpoint_table)
    
    # Top IPs Table
    ip_table = Table(title="Top 5 Client IPs")
    ip_table.add_column("Client IP", style="bold magenta")
    ip_table.add_column("Requests", style="green")
    for ip, count in report['top_ips']:
        ip_table.add_row(ip, str(count))
    console.print(ip_table)

    # Errors Summary
    console.print(Panel(
        f"Total 4xx/5xx Client & Server Errors: [bold red]{report['errors_count']}[/bold red]",
        title="Error Metrics",
        border_style="red"
    ))

if __name__ == "__main__":
    log_file = "access.log"
    
    if not os.path.exists(log_file):
        console.print(f"[yellow]'{log_file}' not found. Generating mock log file...[/yellow]")
        from log_generator import generate_mock_log
        generate_mock_log(log_file, 250)
        
    entries = parse_log_file(log_file)
    if entries:
        report = analyze_logs(entries)
        save_report(report, "report.json")
        display_console_report(report)
