"""Audit trail logging for incident diagnosis queries.

Maintains a local JSON log of every query with full metadata.
Supports display with rich for beautiful terminal output.
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger('incident_agent.audit_log')


class AuditLogger:
    """Structured audit logger for incident diagnosis records."""

    def __init__(self, log_path: str = "audit_log.json"):
        self.log_path = log_path
        self._entries: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Load existing audit log from disk."""
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, 'r') as f:
                    data = json.load(f)
                    self._entries = data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Failed to load audit log: {e}")
            self._entries = []

    def _save(self):
        """Save audit log to disk."""
        try:
            with open(self.log_path, 'w') as f:
                json.dump(self._entries, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save audit log: {e}")

    def log(self, entry: Dict[str, Any]):
        """Add an audit log entry."""
        self._entries.append(entry)
        self._save()

    def mark_resolved(self, incident_id: str):
        """Mark an incident as resolved in the audit log."""
        for entry in self._entries:
            if entry.get('incident_id') == incident_id:
                entry['resolved'] = True
                self._save()
                return True
        return False

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all audit log entries."""
        return self._entries

    def get_recent(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent audit log entries."""
        return self._entries[-count:]

    def get_stats(self) -> Dict[str, Any]:
        """Compute summary statistics from the audit log."""
        if not self._entries:
            return {
                'total_incidents': 0,
                'total_cost': 0.0,
                'avg_cost': 0.0,
                'avg_latency': 0.0,
                'resolved_count': 0,
                'known_count': 0,
                'partial_count': 0,
                'novel_count': 0,
            }

        total_cost = sum(e.get('cost_usd', 0.0) for e in self._entries)
        total_latency = sum(e.get('latency_seconds', 0.0) for e in self._entries)
        resolved = sum(1 for e in self._entries if e.get('resolved', False))
        known = sum(1 for e in self._entries if e.get('incident_type') == 'KNOWN')
        partial = sum(1 for e in self._entries if e.get('incident_type') == 'PARTIAL')
        novel = sum(1 for e in self._entries if e.get('incident_type') == 'NOVEL')
        n = len(self._entries)

        return {
            'total_incidents': n,
            'total_cost': round(total_cost, 6),
            'avg_cost': round(total_cost / n, 6) if n > 0 else 0.0,
            'avg_latency': round(total_latency / n, 2) if n > 0 else 0.0,
            'resolved_count': resolved,
            'known_count': known,
            'partial_count': partial,
            'novel_count': novel,
        }

    def display_table(self):
        """Display audit log as a rich table."""
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text

        console = Console()

        if not self._entries:
            console.print("[yellow]No audit entries found.[/yellow]")
            return

        table = Table(title="Incident Audit Trail", border_style="blue")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Model", style="green")
        table.add_column("Cost ($)", justify="right", style="yellow")
        table.add_column("Cum. Cost ($)", justify="right", style="yellow")
        table.add_column("Latency (s)", justify="right", style="blue")
        table.add_column("Sim. Score", justify="right", style="cyan")
        table.add_column("Resolved", style="green")

        for entry in reversed(self._entries[-20:]):  # Show last 20
            inc_type = entry.get('incident_type', '')
            type_style = {
                'KNOWN': '[green]KNOWN[/green]',
                'PARTIAL': '[yellow]PARTIAL[/yellow]',
                'NOVEL': '[red]NOVEL[/red]',
            }.get(inc_type, inc_type)

            cost = entry.get('cost_usd', 0.0)
            cum_cost = entry.get('cumulative_cost_usd', 0.0)
            latency = entry.get('latency_seconds', 0.0)
            sim = entry.get('similarity_score', 0.0)
            resolved = '[OK]' if entry.get('resolved', False) else '[...]'
            model = entry.get('model_used', '').split('/')[-1][:20]

            table.add_row(
                entry.get('incident_id', ''),
                type_style,
                model,
                f"{cost:.6f}",
                f"{cum_cost:.4f}",
                f"{latency:.1f}",
                f"{sim:.2%}",
                resolved,
            )

        console.print(table)

        # Summary
        stats = self.get_stats()
        console.print(f"\n[bold]Summary:[/bold] "
                      f"Total: {stats['total_incidents']} incidents | "
                      f"Total Cost: ${stats['total_cost']:.6f} | "
                      f"Avg Cost: ${stats['avg_cost']:.6f} | "
                      f"Avg Latency: {stats['avg_latency']:.1f}s | "
                      f"Resolved: {stats['resolved_count']}")
