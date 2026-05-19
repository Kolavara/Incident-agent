#!/usr/bin/env python3
"""CLI entry point for the Incident Response Agent.

Usage:
    python main.py diagnose     - Diagnose an error log
    python main.py resolve      - Mark last incident as resolved
    python main.py history      - Show past incidents
    python main.py audit        - Show audit trail
    python main.py demo         - Run automated demo with synthetic data
"""

import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any

# Fix Windows console encoding before anything else
# On Windows cmd (cp1252), Unicode characters like → crash RichHandler
if sys.platform == 'win32':
    for _stream in [sys.stdout, sys.stderr]:
        if _stream and hasattr(_stream, 'reconfigure'):
            try:
                _stream.reconfigure(encoding='utf-8', errors='backslashreplace')
            except Exception:
                pass

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich import box

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
from logging_config import setup_logging
setup_logging()

from src.processing.preprocessor import LogPreprocessor
from src.rag.vector_store import VectorStore
from src.rag.retriever import IncidentRetriever
from src.rag.indexer import IncidentIndexer
from src.core.model_factory import ModelRouter
from src.inference.inference_engine import InferenceEngine
from src.inference.response_parser import ResponseParser
from audit_log import AuditLogger
from src.remediation.engine import RemediationEngine
from src.remediation.models import FixStatus

logger = logging.getLogger('incident_agent.cli')
console = Console()


def initialize_engine() -> InferenceEngine:
    """Initialize all components and return the inference engine."""
    vector_store = VectorStore()
    model_router = ModelRouter()
    retriever = IncidentRetriever(vector_store)
    indexer = IncidentIndexer(vector_store)
    audit_logger = AuditLogger()
    return InferenceEngine(model_router, retriever, indexer, audit_logger)


def display_diagnosis(result: Dict[str, Any]):
    """Display diagnosis results in a rich panel."""
    diagnosis = result.get('diagnosis', {})
    inc_type = result.get('incident_type', 'UNKNOWN')
    model = result.get('model_used', 'unknown')
    cost = result.get('cost_usd', 0.0)
    latency = result.get('latency_seconds', 0.0)
    sim_score = result.get('similarity_score', 0.0)
    incident_id = result.get('incident_id', '')
    model_tier = result.get('model_tier', '')

    # Status indicator
    type_labels = {
        'KNOWN': ('[+] KNOWN INCIDENT (memory match)', 'green'),
        'PARTIAL': ('[?] PARTIAL MATCH (verify suggested)', 'yellow'),
        'NOVEL': ('[!] NOVEL INCIDENT (first seen)', 'red'),
    }
    status_text, status_color = type_labels.get(inc_type, ('UNKNOWN', 'white'))

    # Build content
    content_lines = []
    content_lines.append(f"[bold]Status[/bold]    : [{status_color}]{status_text}[/{status_color}]")
    content_lines.append(f"[bold]Incident ID[/bold]: {incident_id}")
    content_lines.append(f"[bold]Similarity[/bold] : {sim_score:.2%}")
    content_lines.append(f"[bold]Model[/bold]     : {model} ({model_tier})")
    content_lines.append(f"[bold]Cost[/bold]      : ${cost:.6f}")
    content_lines.append(f"[bold]Latency[/bold]   : {latency:.1f}s")
    content_lines.append("")

    # Routing reason
    routing = result.get('routing_reason', '')
    if routing:
        content_lines.append(f"[dim]{routing}[/dim]")
        content_lines.append("")

    # Diagnosis details
    if diagnosis.get('root_cause'):
        content_lines.append(f"[bold]ROOT CAUSE:[/bold] {diagnosis['root_cause']}")
    if diagnosis.get('confidence'):
        conf_color = {'High': 'green', 'Medium': 'yellow', 'Low': 'red'}.get(
            diagnosis['confidence'], 'white'
        )
        content_lines.append(f"[bold]CONFIDENCE:[/bold] [{conf_color}]{diagnosis['confidence']}[/{conf_color}]")

    if diagnosis.get('fix_steps'):
        content_lines.append("")
        content_lines.append("[bold]FIX STEPS:[/bold]")
        for i, step in enumerate(diagnosis['fix_steps'], 1):
            content_lines.append(f"  {i}. {step}")

    if diagnosis.get('notes'):
        content_lines.append("")
        content_lines.append(f"[bold]NOTES:[/bold] {diagnosis['notes']}")

    # Memory context info
    memory = result.get('memory_context', {})
    matches = memory.get('matches', [])
    if matches:
        content_lines.append("")
        content_lines.append("[dim]Past incidents in context:[/dim]")
        for m in matches[:2]:
            rc = m.get('metadata', {}).get('root_cause', 'unknown')
            sim = m.get('similarity', 0.0)
            content_lines.append(f"  [dim]* {rc} (sim: {sim:.2%})[/dim]")

    panel = Panel(
        '\n'.join(content_lines),
        title=f"[bold]INCIDENT DIAGNOSIS #{incident_id}[/bold]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )

    console.print(panel)


def cmd_diagnose():
    """Accept multiline input and diagnose the error."""
    console.print("[bold cyan][>>] Incident Diagnosis[/bold cyan]")
    console.print("Paste or type your error log below. Press [bold]Ctrl+D[/bold] (or type END on a new line) when done.\n")

    # Read multiline input
    lines = []
    try:
        while True:
            line = input()
            if line.strip().upper() == 'END':
                break
            lines.append(line)
    except EOFError:
        pass

    raw_log = '\n'.join(lines).strip()

    if not raw_log or len(raw_log) < 20:
        console.print("[red]Error: Input too short. Please provide a detailed error log (at least 20 characters).[/red]")
        return

    # Validate input
    preprocessor = LogPreprocessor()
    if not preprocessor.validate_input(raw_log):
        console.print("[red]Error: Invalid input. Please provide a proper error log.[/red]")
        return

    # Process with spinner
    try:
        engine = initialize_engine()

        with console.status("[bold cyan]Analyzing incident...", spinner="dots") as status:
            status.update("[cyan]Step 1/3: Preprocessing log...")
            time.sleep(0.3)

            status.update("[cyan]Step 2/3: Searching memory and routing model...")
            time.sleep(0.5)

            status.update("[cyan]Step 3/3: Running LLM diagnosis...")
            result = engine.diagnose(raw_log)

        console.print()
        display_diagnosis(result)

        # Show cumulative cost warning
        cumulative = result.get('cumulative_cost_usd', 0.0)
        budget_cap = engine.model_router.get_budget_cap()
        if cumulative > budget_cap * 0.8:
            console.print(
                f"[yellow][!] Budget warning: ${cumulative:.4f} / ${budget_cap:.2f} used "
                f"({(cumulative / budget_cap * 100):.0f}%)[/yellow]"
            )
        elif engine.model_router.is_budget_exhausted():
            console.print(
                "[yellow][!] Budget cap reached. Subsequent diagnoses will use local Ollama model.[/yellow]"
            )

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error during diagnosis: {e}[/red]")
        logger.exception("Diagnosis failed")


def cmd_resolve():
    """Mark the last incident as resolved."""
    engine = initialize_engine()

    if not hasattr(engine, '_last_incident_id') or not engine._last_incident_id:
        console.print("[yellow]No previous incident to resolve. Run 'diagnose' first.[/yellow]")
        return

    console.print("[bold green][OK] Resolve Incident[/bold green]")
    console.print(f"Resolving incident: {engine._last_incident_id}")

    fix = Prompt.ask("[bold]What fix was applied?[/bold]")
    if not fix or fix.upper() == 'SKIP':
        console.print("[yellow]Skipped.[/yellow]")
        return

    time_str = Prompt.ask("[bold]Resolution time (minutes)[/bold]", default="0")
    try:
        resolution_time = int(time_str)
    except ValueError:
        resolution_time = 0

    if engine.resolve_last(fix, resolution_time):
        console.print("[green][OK] Incident stored in memory. The agent will learn from this for future diagnoses![/green]")
    else:
        console.print("[red]Failed to store resolution.[/red]")


def cmd_history():
    """Show all past incidents from memory."""
    engine = initialize_engine()
    vector_store = engine.retriever.vector_store
    all_incidents = vector_store.get_all()

    if not all_incidents:
        console.print("[yellow]No past incidents found in memory.[/yellow]")
        return

    table = Table(title="Past Incidents", border_style="green", box=box.ROUNDED)
    table.add_column("#", style="cyan")
    table.add_column("Root Cause", style="bold")
    table.add_column("Service", style="blue")
    table.add_column("Fix Applied", style="green")
    table.add_column("Resolution (min)", justify="right", style="yellow")
    table.add_column("Model", style="magenta")
    table.add_column("Cost ($)", justify="right", style="yellow")

    for i, incident in enumerate(all_incidents, 1):
        meta = incident.get('metadata', {})
        table.add_row(
            str(i),
            meta.get('root_cause', 'N/A')[:50],
            meta.get('service', 'N/A'),
            meta.get('fix_applied', 'N/A')[:40],
            str(meta.get('resolution_time_minutes', 'N/A')),
            meta.get('model_used', 'N/A')[:20],
            f"{meta.get('cost_usd', 0.0):.6f}",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(all_incidents)} incidents stored[/dim]")


def cmd_audit():
    """Show the full audit trail."""
    audit_logger = AuditLogger()
    audit_logger.display_table()


def cmd_demo():
    """Run automated demo with synthetic data (requires API keys)."""
    console.print(Panel.fit(
        "[bold cyan]>> Incident Agent Demo <<[/bold cyan]\n"
        "[dim]Running automated demonstration with synthetic PayStream Inc data...[/dim]",
        box=box.ROUNDED,
    ))

    # Load demo data
    demo_path = "data/demo_incidents.json"
    try:
        with open(demo_path, 'r') as f:
            demo_incidents = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Demo data not found at {demo_path}[/red]")
        return

    if not demo_incidents:
        console.print("[red]No demo incidents loaded![/red]")
        return

    # Initialize fresh engine for demo
    vector_store = VectorStore()
    model_router = ModelRouter()
    retriever = IncidentRetriever(vector_store)
    indexer = IncidentIndexer(vector_store)
    audit_logger = AuditLogger()
    engine = InferenceEngine(model_router, retriever, indexer, audit_logger)

    # Phase 1: Build memory with incidents 1-10
    console.print(f"\n[bold cyan]Phase 1: Building memory with {min(10, len(demo_incidents))} incidents...[/bold cyan]")

    # Pre-store incidents 1-10 in memory
    for i, incident in enumerate(demo_incidents[:10], 1):
        metadata = {
            'root_cause': incident.get('root_cause', 'unknown'),
            'fix_applied': incident.get('fix', 'unknown'),
            'service': incident.get('service', 'unknown'),
            'resolved': True,
            'resolution_time_minutes': incident.get('resolution_time_minutes', 0),
            'model_used': 'preloaded',
            'cost_usd': 0.0,
            'timestamp': incident.get('timestamp', '2025-01-01T00:00:00'),
        }
        vector_store.store(
            content=incident.get('raw_log', ''),
            metadata=metadata,
        )
        console.print(f"  [dim]Stored INC-{i:03d}: {incident.get('root_cause', '')[:50]}...[/dim]")

    console.print(f"\n[green][OK] Memory built. {len(demo_incidents[:10])} incidents stored. Starting live demo...[/green]\n")
    time.sleep(1)

    # Phase 2: Run demo incidents 11-13 with full output
    demo_indices = [10, 11, 12]  # 0-indexed: 11th, 12th, 13th incidents

    for idx in demo_indices:
        if idx >= len(demo_incidents):
            continue

        incident = demo_incidents[idx]
        raw_log = incident.get('raw_log', '')
        expected_rc = incident.get('root_cause', '')

        console.print(f"\n[bold]" + "-" * 45)
        console.print(f"[bold]>> Diagnosing: {incident.get('id', f'INC-{idx+1:03d}')}[/bold]")
        console.print(f"[dim]Incident: {expected_rc[:60]}...[/dim]")
        console.print(f"[bold]" + "-" * 45)

        try:
            with console.status("[cyan]Diagnosing...", spinner="dots") as status:
                result = engine.diagnose(raw_log)

            display_diagnosis(result)

            # Auto-resolve for demo
            engine.resolve_last(
                fix_applied=incident.get('fix', 'Applied standard fix'),
                resolution_time_minutes=incident.get('resolution_time_minutes', 15),
            )

        except Exception as e:
            console.print(f"[red]Error diagnosing incident {incident.get('id', 'unknown')}: {e}[/red]")

        time.sleep(1)

    # Phase 3: Show audit trail
    console.print(f"\n\n[bold cyan]Final Audit Trail[/bold cyan]")
    audit_logger.display_table()

    # Phase 4: Show cost summary
    console.print(f"\n[bold cyan]Cost Analysis[/bold cyan]")
    stats = audit_logger.get_stats()
    entries = audit_logger.get_all()

    # Split into first 3 and remaining queries
    first_3 = entries[:3]
    rest = entries[3:] if len(entries) > 3 else []

    avg_first_3 = sum(e.get('cost_usd', 0.0) for e in first_3) / len(first_3) if first_3 else 0.0
    avg_rest = sum(e.get('cost_usd', 0.0) for e in rest) / len(rest) if rest else 0.0

    table = Table(border_style="yellow", box=box.SIMPLE)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total incidents analyzed", str(stats['total_incidents']))
    table.add_row("Total cost", f"${stats['total_cost']:.6f}")
    table.add_row("Average cost per incident", f"${stats['avg_cost']:.6f}")
    table.add_row("Average latency", f"{stats['avg_latency']:.1f}s")
    table.add_row("")
    table.add_row("Average cost (first 3 queries)", f"${avg_first_3:.6f}")
    table.add_row("Average cost (remaining queries)", f"${avg_rest:.6f}")

    if avg_first_3 > 0 and avg_rest > 0:
        savings = ((avg_first_3 - avg_rest) / avg_first_3) * 100
        table.add_row(
            "[green]Cost reduction from memory[/green]",
            f"[green]{savings:.0f}%[/green]"
        )

    console.print(table)

    # Summary message
    console.print(f"\n[bold cyan]Demo Complete![/bold cyan]")
    console.print(
        f"Total spent: ${stats['total_cost']:.6f} | "
        f"Average cost query 1-3: ${avg_first_3:.6f} | "
        f"Average cost query 4-7: ${avg_rest:.6f}"
    )
    console.print(
        "[dim]The agent learns from past incidents, so similar incidents use the cheaper model. "
        "This demonstrates the cost-saving power of Hindsight memory + cascadeflow routing![/dim]"
    )


def cmd_demo_offline():
    """Run demo without LLM API calls using predefined responses."""
    console.print(Panel.fit(
        "[bold cyan]>> Incident Agent Demo (Offline Mode) <<[/bold cyan]\n"
        "[dim]Running in OFFLINE mode - using simulated responses (no API calls)[/dim]\n"
        "[yellow]! No API keys required for this mode[/yellow]",
        box=box.ROUNDED,
    ))

    # Load demo data
    demo_path = "data/demo_incidents.json"
    try:
        with open(demo_path, 'r') as f:
            demo_incidents = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Demo data not found at {demo_path}[/red]")
        return

    if not demo_incidents:
        console.print("[red]No demo incidents loaded![/red]")
        return

    # Initialize fresh engine for demo
    vector_store = VectorStore()
    model_router = ModelRouter()
    retriever = IncidentRetriever(vector_store)
    indexer = IncidentIndexer(vector_store)
    audit_logger = AuditLogger()
    engine = InferenceEngine(model_router, retriever, indexer, audit_logger)

    # Phase 1: Build memory with incidents 1-10
    console.print(f"\n[bold cyan]Phase 1: Building memory with {min(10, len(demo_incidents))} incidents...[/bold cyan]")

    for i, incident in enumerate(demo_incidents[:10], 1):
        metadata = {
            'root_cause': incident.get('root_cause', 'unknown'),
            'fix_applied': incident.get('fix', 'unknown'),
            'service': incident.get('service', 'unknown'),
            'resolved': True,
            'resolution_time_minutes': incident.get('resolution_time_minutes', 0),
            'model_used': 'preloaded',
            'cost_usd': 0.0,
            'timestamp': incident.get('timestamp', '2025-01-01T00:00:00'),
        }
        vector_store.store(
            content=incident.get('raw_log', ''),
            metadata=metadata,
        )
        console.print(f"  [dim]Stored INC-{i:03d}: {incident.get('root_cause', '')[:50]}...[/dim]")

    console.print(f"\n[green][OK] Memory built. {len(demo_incidents[:10])} incidents stored. Starting live demo...[/green]\n")
    time.sleep(1)

    # Phase 2: Process demo incidents 11-13 using offline simulation
    parser = ResponseParser()
    demo_indices = [10, 11, 12]

    for idx in demo_indices:
        if idx >= len(demo_incidents):
            continue

        incident = demo_incidents[idx]
        raw_log = incident.get('raw_log', '')
        expected_rc = incident.get('root_cause', '')

        console.print(f"\n[bold]" + "-" * 45)
        console.print(f"[bold]>> Diagnosing: {incident.get('id', f'INC-{idx+1:03d}')}[/bold]")
        console.print(f"[dim]Incident: {expected_rc[:60]}...[/dim]")
        console.print(f"[bold]" + "-" * 45)

        # Simulate preprocessing
        preprocessor = LogPreprocessor()
        processed = preprocessor.preprocess(raw_log)
        cleaned_log = processed['cleaned_log']

        # Simulate retrieval
        mem_result = retriever.retrieve(cleaned_log)
        sim_score = mem_result['top_score']
        inc_type = mem_result['incident_type']

        # Determine which model would be used
        if sim_score >= 0.8:
            model_name = "llama3-8b-8192 (cheap)"
            model_tier = "cheap"
            cost = 0.001
        elif sim_score >= 0.5:
            model_name = "llama3-8b-8192 (cheap)"
            model_tier = "cheap"
            cost = 0.001
        else:
            model_name = "qwen-qwen3-32b (powerful)"
            model_tier = "powerful"
            cost = 0.031

        # Simulate the diagnosis
        diagnosis_text = (
            f"ROOT CAUSE: {incident.get('root_cause', 'Unknown')}\n"
            f"CONFIDENCE: High\n"
            f"FIX STEPS:\n"
            f"1. {incident.get('fix', 'Apply standard fix')}\n"
            f"2. Monitor the service for 5 minutes\n"
            f"3. Check related services for cascading effects\n"
            f"NOTES: This issue was identified and resolved."
        )

        diagnosis = parser.parse_diagnosis(diagnosis_text)

        # Build result dict
        result = {
            'incident_id': incident.get('id', f'INC-{idx+1:03d}'),
            'diagnosis': diagnosis,
            'incident_type': inc_type,
            'similarity_score': round(sim_score, 4),
            'model_used': model_name,
            'model_tier': model_tier,
            'routing_reason': f"{inc_type} incident (similarity={sim_score:.2f}) - using {model_tier} model",
            'cost_usd': cost,
            'cumulative_cost_usd': cost,
            'latency_seconds': round(1.0 + (0.5 if model_tier == 'powerful' else 0.0), 2),
            'input_tokens': 500,
            'output_tokens': 150,
            'memory_context': mem_result,
            'raw_response': diagnosis_text,
            'extracted_fields': processed,
        }

        display_diagnosis(result)

        time.sleep(1)

    # Phase 3: Show audit simulation
    console.print(f"\n\n[bold cyan]Audit Trail (Simulated)[/bold cyan]")

    audit_table = Table(title="Incident Audit Trail (Simulated)", border_style="blue")
    audit_table.add_column("ID", style="cyan")
    audit_table.add_column("Incident Type", style="magenta")
    audit_table.add_column("Model", style="green")
    audit_table.add_column("Cost ($)", justify="right", style="yellow")
    audit_table.add_column("Latency (s)", justify="right", style="blue")

    for i, idx in enumerate(demo_indices):
        if idx >= len(demo_incidents):
            continue
        inc = demo_incidents[idx]
        sim = retriever.retrieve(inc.get('raw_log', ''))['top_score']
        inc_type = 'KNOWN' if sim >= 0.8 else ('PARTIAL' if sim >= 0.5 else 'NOVEL')
        model = 'llama3-8b-8192' if inc_type != 'NOVEL' else 'qwen-qwen3-32b'
        cost = 0.001 if inc_type != 'NOVEL' else 0.031
        latency = 0.9 if inc_type != 'NOVEL' else 2.5

        type_display = {
            'KNOWN': '[green]KNOWN[/green]',
            'PARTIAL': '[yellow]PARTIAL[/yellow]',
            'NOVEL': '[red]NOVEL[/red]',
        }.get(inc_type, inc_type)

        audit_table.add_row(
            inc.get('id', f'INC-{idx+1:03d}'),
            type_display,
            model,
            f"{cost:.3f}",
            f"{latency:.1f}",
        )

    console.print(audit_table)

    # Phase 4: Summary
    console.print(f"\n[bold cyan]Demo Complete! (Offline Mode)[/bold cyan]")
    console.print(
        f"Total incidents: {len(demo_indices)} | "
        f"Memory matches: 2 (Redis errors) | "
        f"Novel incidents: 1\n"
        f"[green]Cost without memory: ~$0.093 (3 x $0.031 using powerful model)[/green]\n"
        f"[green]Cost with memory:    ~$0.033 (2 x $0.001 cheap + 1 x $0.031 powerful)[/green]\n"
        f"[bold]Savings: ~65% from Hindsight memory + cascadeflow routing![/bold]"
    )
    console.print(
        "\n[dim]This simulation shows how the agent learns from past incidents. "
        "When a known Redis connection pool error appears again, "
        "the agent recognizes it and routes to the cheap model instead of the powerful one.[/dim]"
    )


def _load_last_diagnosis():
    """Load the most recent unresolved diagnosis from the audit log.

    Returns:
        Dict with diagnosis_result fields, or None if nothing found
    """
    audit_logger = AuditLogger()
    entries = audit_logger.get_all()

    # Find the most recent unresolved entry
    for entry in reversed(entries):
        if not entry.get('resolved', False):
            return _build_diagnosis_result(entry)

    return None


def _build_diagnosis_result(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build a diagnosis_result dict from an audit log entry.

    Args:
        entry: An audit log entry dict

    Returns:
        Dict compatible with InferenceEngine.diagnose() output
    """
    result = {
        'incident_id': entry.get('incident_id', 'UNKNOWN'),
        'incident_type': entry.get('incident_type', 'NOVEL'),
        'diagnosis': {
            'root_cause': entry.get('root_cause', ''),
            'confidence': entry.get('confidence', 'Medium'),
            'fix_steps': [],
            'notes': '',
        },
        'extracted_fields': {
            'service': entry.get('service', 'unknown'),
            'error_type': entry.get('error_type', 'unknown'),
        },
    }

    # Prefer direct fix_steps from the entry (most reliable)
    direct_steps = entry.get('fix_steps', [])
    if direct_steps:
        result['diagnosis']['fix_steps'] = direct_steps
    else:
        # Fallback: parse fix steps from the raw LLM response
        raw_response = entry.get('raw_response', '')
        if raw_response:
            parser = ResponseParser()
            parsed = parser.parse_diagnosis(raw_response)
            result['diagnosis']['fix_steps'] = parsed.get('fix_steps', [])
            result['diagnosis']['notes'] = parsed.get('notes', '')

    return result


def cmd_remediate():
    """Run the full remediation pipeline on the last diagnosis result.

    Steps 5-10:
    5. Generate implementation tasks from fix steps
    6. Generate validation tests
    7. Implement fixes in the target repo
    8. Run validation tests
    9. Create PR-ready code (local git branch)
    10. Push to GitHub (if configured)
    """
    diagnosis_result = _load_last_diagnosis()

    if not diagnosis_result:
        # Fallback: try using last demo incident
        try:
            demo_path = "data/demo_incidents.json"
            if Path(demo_path).exists():
                with open(demo_path, 'r') as f:
                    demo_data = json.load(f)
                if demo_data:
                    last_entry = demo_data[-1]
                    console.print("[yellow]No recent diagnosis found. Using last demo incident.[/yellow]")
                    # Build a minimal diagnosis_result from demo data
                    diagnosis_result = {
                        'incident_id': last_entry.get('id', 'INC-DEMO'),
                        'incident_type': 'KNOWN',
                        'diagnosis': {
                            'root_cause': last_entry.get('root_cause', ''),
                            'confidence': 'High',
                            'fix_steps': [last_entry.get('fix', 'Apply standard fix')],
                            'notes': '',
                        },
                        'extracted_fields': {
                            'service': last_entry.get('service', 'unknown'),
                            'error_type': 'unknown',
                        },
                    }
        except (json.JSONDecodeError, IOError):
            pass

    if not diagnosis_result:
        console.print("[red]No recent diagnosis found. Run 'diagnose' first, or use 'remediate-demo'.[/red]")
        return

    root_cause = diagnosis_result.get('diagnosis', {}).get('root_cause', 'Unknown')

    console.print(
        Panel.fit(
            f"[bold cyan]>> Remediation Pipeline (Steps 5-10) <<[/bold cyan]\n"
            f"[dim]Auto-remediating: {root_cause[:60]}[/dim]",
            box=box.ROUNDED,
        )
    )

    if not diagnosis_result['diagnosis']['fix_steps']:
        console.print("[yellow]No fix steps found in the diagnosis. Cannot generate remediation plan.[/yellow]")
        return

    try:
        engine = RemediationEngine()

        with console.status("[bold cyan]Running remediation pipeline...", spinner="dots") as status:
            status.update("[cyan]Step 5/10: Generating implementation tasks...")
            plan = engine.plan(diagnosis_result)

            if not plan.tasks:
                console.print("[red]Could not generate any fix tasks from the diagnosis.[/red]")
                return

            # Display plan
            console.print()
            _display_remediation_plan(plan)

            # Confirm before proceeding
            if not Prompt.ask("\n[bold]Apply these fixes?[/bold]", choices=["y", "n"], default="n") == "y":
                console.print("[yellow]Remediation cancelled.[/yellow]")
                return

            # Steps 6-7: Apply fixes and generate tests
            status.update("[cyan]Steps 6-7: Applying fixes and generating tests...")
            engine.apply(plan)

            # Step 8: Validate
            status.update("[cyan]Step 8: Running validation tests...")
            validation = engine.validate(plan)

            # Steps 9-10: Create PR and push
            status.update("[cyan]Steps 9-10: Creating PR and pushing...")
            pr_result = engine.create_pr(plan)

        # Show results
        console.print()
        _display_remediation_result(plan, validation, pr_result)

    except Exception as e:
        console.print(f"[red]Remediation failed: {e}[/red]")
        logger.exception("Remediation failed")


def cmd_remediate_plan():
    """Generate and display a remediation plan without applying changes."""
    diagnosis_result = _load_last_diagnosis()

    if not diagnosis_result:
        console.print("[yellow]No recent diagnosis found. Run 'diagnose' first.[/yellow]")
        return

    if not diagnosis_result['diagnosis']['fix_steps']:
        console.print("[yellow]No fix steps found in the diagnosis.[/yellow]")
        return

    engine = RemediationEngine()
    plan = engine.plan(diagnosis_result)

    if plan.tasks:
        _display_remediation_plan(plan)
        console.print(f"\n[dim]Run 'remediate' to apply these fixes.[/dim]")
    else:
        console.print("[yellow]Could not generate any fix tasks.[/yellow]")


def cmd_remediate_demo():
    """Run the full remediation pipeline on demo incidents.

    Demonstrates steps 5-10 end-to-end using the demo incidents.
    """
    demo_path = "data/demo_incidents.json"
    try:
        with open(demo_path, 'r') as f:
            demo_incidents = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Demo data not found at {demo_path}[/red]")
        return

    if not demo_incidents:
        console.print("[red]No demo incidents loaded![/red]")
        return

    console.print(Panel.fit(
        "[bold cyan]>> Remediation Demo (Steps 5-10) <<[/bold cyan]\n"
        "[dim]Demonstrating auto-remediation on PayStream incidents...[/dim]",
        box=box.ROUNDED,
    ))

    engine = RemediationEngine()

    # Use the last 3 demo incidents (varied types)
    demo_indices = [12, 13, 14]  # 0-indexed

    for idx in demo_indices:
        if idx >= len(demo_incidents):
            continue

        incident = demo_incidents[idx]
        console.print(f"\n[bold]" + "-" * 50)
        console.print(f"[bold]>> Remediating: {incident.get('id', f'INC-{idx+1:03d}')}[/bold]")
        console.print(f"[dim]{incident.get('root_cause', '')}[/dim]")
        console.print(f"[bold]" + "-" * 50)

        # Build a diagnosis result for the demo
        fix_steps = [incident.get('fix', 'Apply standard fix')]

        diagnosis_result = {
            'incident_id': incident.get('id', f'INC-{idx+1:03d}'),
            'incident_type': 'KNOWN' if idx <= 12 else 'NOVEL',
            'diagnosis': {
                'root_cause': incident.get('root_cause', ''),
                'confidence': 'High',
                'fix_steps': fix_steps,
                'notes': f"Auto-remediation for {incident.get('service', 'unknown')}",
            },
            'extracted_fields': {
                'service': incident.get('service', 'unknown'),
                'error_type': 'connection_pool_exhausted' if 'redis' in incident.get('root_cause', '').lower() else 'unknown',
            },
        }

        try:
            # Step 5: Plan
            with console.status("[cyan]Generating remediation plan...", spinner="dots"):
                plan = engine.plan(diagnosis_result)

            if plan.tasks:
                console.print(f"[green]  [OK] Generated {len(plan.tasks)} fix task(s)")
                for t in plan.tasks:
                    console.print(f"    - {t.description[:60]} ({t.change_type.value})")

                # Steps 6-7: Apply + tests
                with console.status("[cyan]Applying fixes...", spinner="dots"):
                    engine.apply(plan)

                applied = sum(1 for t in plan.tasks if t.status == FixStatus.APPLIED)
                console.print(f"[green]  [OK] Applied {applied} fix task(s)")

                # Step 8: Validate
                with console.status("[cyan]Running validation...", spinner="dots"):
                    v = engine.validate(plan)

                v_status = "[green][PASS]" if v.passed else "[red][FAIL]"
                console.print(f"  {v_status} ({v.passed_tests}/{v.total_tests} tests passed)")

                # Steps 9-10: PR
                with console.status("[cyan]Creating PR...", spinner="dots"):
                    pr = engine.create_pr(plan)

                if pr.success:
                    console.print(f"[green]  [OK] PR ready: {pr.pr_url or 'local branch'}[/green]")
                else:
                    console.print(f"[yellow]  ! PR creation: {pr.error or 'local only'}[/yellow]")
            else:
                console.print("[yellow]  ! No tasks generated (unmatched fix pattern)[/yellow]")

        except Exception as e:
            console.print(f"[red]  [ERR] Error: {e}[/red]")

    console.print(f"\n[bold cyan]Demo Remediation Complete![/bold cyan]")
    console.print(f"[dim]All changes committed to local git branches in fixes/paystream/[/dim]")
    console.print(f"[dim]Set GITHUB_TOKEN to enable automatic PR creation on GitHub.[/dim]")


def _display_remediation_plan(plan):
    """Display a remediation plan in a rich panel."""
    lines = []
    lines.append(f"[bold]Branch:[/bold] {plan.branch_name}")
    lines.append(f"[bold]PR Title:[/bold] {plan.pr_title}")
    lines.append("")
    lines.append("[bold]Fix Tasks:[/bold]")

    for i, task in enumerate(plan.tasks, 1):
        type_icon = {
            'config_edit': '[CONFIG]',
            'code_edit': '[CODE]',
            'file_create': '[NEW]',
            'k8s_manifest': '[K8S]',
            'script_run': '[EXEC]',
        }.get(task.change_type.value, '[FIX]')

        lines.append(f"  {i}. {type_icon} {task.description}")
        if task.file_path:
            lines.append(f"     [dim]File: {task.file_path}[/dim]")
        if task.command:
            lines.append(f"     [dim]Command: {task.command}[/dim]")

    panel = Panel(
        '\n'.join(lines),
        title=f"[bold]REMEDIATION PLAN #{plan.incident_id}[/bold]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


def _display_remediation_result(plan, validation, pr_result):
    """Display the final remediation result."""
    # Task summary
    total = len(plan.tasks)
    applied = sum(1 for t in plan.tasks if t.status == FixStatus.APPLIED)
    failed = sum(1 for t in plan.tasks if t.status == FixStatus.FAILED)
    skipped = sum(1 for t in plan.tasks if t.status == FixStatus.SKIPPED)

    lines = []
    lines.append(f"[bold]Tasks:[/bold] {total} total")
    lines.append(f"[green]  Applied: {applied}[/green]")
    if failed:
        lines.append(f"[red]  Failed: {failed}[/red]")
    if skipped:
        lines.append(f"[yellow]  Skipped: {skipped}[/yellow]")
    lines.append("")

    # Validation summary
    v_text = "PASSED" if validation.passed else "FAILED"
    v_color = "green" if validation.passed else "red"
    lines.append(f"[bold]Validation:[/bold] [{v_color}]{v_text}[/{v_color}]")
    lines.append(f"  {validation.passed_tests}/{validation.total_tests} tests passed")
    lines.append("")

    # PR summary
    if pr_result and pr_result.success:
        lines.append(f"[bold]Pull Request:[/bold] [green]Created[/green]")
        if pr_result.pr_url:
            lines.append(f"  URL: {pr_result.pr_url}")
        if pr_result.branch_url:
            lines.append(f"  Branch: {pr_result.branch_url}")
    else:
        lines.append(f"[bold]Pull Request:[/bold] [yellow]Local only[/yellow]")
        lines.append(f"  Branch: {plan.branch_name}")
        lines.append(f"  [dim]Set GITHUB_TOKEN env var for auto-push[/dim]")

    panel = Panel(
        '\n'.join(lines),
        title="[bold]REMEDIATION RESULT[/bold]",
        border_style="blue",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)

    # Show diff hint
    diff_path = Path("fixes/paystream/")
    console.print(f"\n[dim]Changes applied in: {diff_path.resolve()}[/dim]")


def main():
    """Main CLI entry point."""
    console.print(Panel.fit(
        "[bold cyan]>> Incident Response Agent <<[/bold cyan]\n"
        "[dim]AI-powered SRE assistant with persistent memory and auto-remediation[/dim]",
        box=box.ROUNDED,
    ))

    if len(sys.argv) < 2:
        console.print("\n[bold]Commands:[/bold]")
        console.print("  [cyan]diagnose[/cyan]        Paste/type an error log and get a diagnosis")
        console.print("  [cyan]diagnose-mock[/cyan]    Diagnose via offline simulation")
        console.print("  [cyan]resolve[/cyan]         Mark the last diagnosis as resolved (stores in memory)")
        console.print("  [cyan]history[/cyan]         Show all past incidents stored in memory")
        console.print("  [cyan]audit[/cyan]           Show the full audit trail table")
        console.print("  [cyan]demo[/cyan]            Run the automated diagnosis demo (requires API keys)")
        console.print("  [cyan]demo-offline[/cyan]    Run diagnosis demo without API calls")
        console.print("\n[bold]Remediation Commands (Steps 5-10):[/bold]")
        console.print("  [cyan]remediate[/cyan]        Run full remediation: plan → fix → test → PR → push")
        console.print("  [cyan]remediate-plan[/cyan]   Show remediation plan without applying changes")
        console.print("  [cyan]remediate-demo[/cyan]   Demo auto-remediation on synthetic incidents")
        console.print("\nExample: python main.py remediate")
        return

    command = sys.argv[1].lower()

    commands = {
        'diagnose': cmd_diagnose,
        'diagnose-mock': cmd_demo_offline,
        'resolve': cmd_resolve,
        'history': cmd_history,
        'audit': cmd_audit,
        'demo': cmd_demo,
        'demo-offline': cmd_demo_offline,
        'remediate': cmd_remediate,
        'remediate-plan': cmd_remediate_plan,
        'remediate-demo': cmd_remediate_demo,
    }

    if command in commands:
        commands[command]()
    else:
        console.print(f"[red]Unknown command: {command}[/red]")
        console.print("Available: diagnose, resolve, history, audit, demo, demo-offline, remediate, remediate-plan, remediate-demo")


if __name__ == '__main__':
    main()
