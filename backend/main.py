"""FastAPI backend for the Incident Response Agent."""

import sys
import os
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

# Load environment
load_dotenv()

# Fix Windows console encoding
if sys.platform == 'win32':
    for _stream in [sys.stdout, sys.stderr]:
        if _stream and hasattr(_stream, 'reconfigure'):
            try:
                _stream.reconfigure(encoding='utf-8', errors='backslashreplace')
            except Exception:
                pass

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
from logging_config import setup_logging
setup_logging()

logger = logging.getLogger('incident_agent.api')

# Import project modules
from src.remediation.engine import RemediationEngine
from src.remediation.models import (
    RemediationPlan, FixTask, RemediationResult,
    ValidationResult, PRResult,
)
from src.inference.inference_engine import InferenceEngine
from src.rag.vector_store import VectorStore
from src.core.model_factory import ModelRouter
from src.rag.retriever import IncidentRetriever
from src.rag.indexer import IncidentIndexer
from audit_log import AuditLogger

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class DiagnoseRequest(BaseModel):
    error_log: str = Field(..., min_length=20, description="The error log to diagnose")
    use_llm: bool = Field(True, description="Use real LLM (requires API key) or simulated")

class DiagnoseResponse(BaseModel):
    incident_id: str
    incident_type: str
    similarity_score: float
    root_cause: str
    confidence: str
    fix_steps: List[str]
    notes: str
    model_used: str
    model_tier: str
    cost_usd: float
    latency_seconds: float
    routing_reason: str

class RemediateRequest(BaseModel):
    incident_id: str
    root_cause: str
    fix_steps: List[str]
    incident_type: str = "NOVEL"

class TaskResponse(BaseModel):
    id: str
    description: str
    change_type: str
    file_path: str
    status: str
    priority: int

class PlanResponse(BaseModel):
    incident_id: str
    branch_name: str
    pr_title: str
    tasks: List[TaskResponse]
    summary: str

class ApplyResponse(BaseModel):
    success: bool
    applied: int
    failed: int
    test_tasks_generated: int

class ValidateResponse(BaseModel):
    passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    errors: List[str]
    output: str

class PRResponse(BaseModel):
    success: bool
    branch_url: str
    pr_url: str
    pr_number: Optional[int] = None
    error: Optional[str] = None

class RemediateRunResponse(BaseModel):
    plan: PlanResponse
    apply: ApplyResponse
    validation: ValidateResponse
    pr: PRResponse
    error: Optional[str] = None

class HistoryEntry(BaseModel):
    incident_id: str
    incident_type: str
    root_cause: str
    service: str
    fix_applied: str
    resolution_time_minutes: int
    model_used: str
    cost_usd: float
    timestamp: str

class AuditEntry(BaseModel):
    incident_id: str
    incident_type: str
    root_cause: str
    model_used: str
    cost_usd: float
    latency_seconds: float
    timestamp: str
    resolved: bool

# ---------------------------------------------------------------------------
# Background engine instances (lazy-initialized)
# ---------------------------------------------------------------------------

_engine: Optional[InferenceEngine] = None
_remediation_engine: Optional[RemediationEngine] = None
_audit_logger: Optional[AuditLogger] = None

def get_inference_engine() -> InferenceEngine:
    global _engine
    if _engine is None:
        vector_store = VectorStore()
        model_router = ModelRouter()
        retriever = IncidentRetriever(vector_store)
        indexer = IncidentIndexer(vector_store)
        audit_logger = AuditLogger()
        _engine = InferenceEngine(model_router, retriever, indexer, audit_logger)
    return _engine

def get_remediation_engine() -> RemediationEngine:
    global _remediation_engine
    if _remediation_engine is None:
        _remediation_engine = RemediationEngine()
    return _remediation_engine

def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger

# ---------------------------------------------------------------------------
# Demo data loader
# ---------------------------------------------------------------------------

_demo_incidents: List[Dict] = []

def load_demo_incidents() -> List[Dict]:
    global _demo_incidents
    if not _demo_incidents:
        demo_path = PROJECT_ROOT / "data" / "demo_incidents.json"
        if demo_path.exists():
            with open(demo_path) as f:
                _demo_incidents = json.load(f)
    return _demo_incidents

def simulate_diagnosis(error_log: str) -> dict:
    """Run offline simulation (no LLM call)."""
    import re
    from src.processing.preprocessor import LogPreprocessor
    from src.inference.response_parser import ResponseParser

    preprocessor = LogPreprocessor()
    processed = preprocessor.preprocess(error_log)
    cleaned_log = processed['cleaned_log']

    # Simple keyword-based root cause detection
    rc_patterns = [
        (r'(?i)redis.*(?:pool|connect|exhaust)', "Redis connection pool exhausted"),
        (r'(?i)dns.*(?:resolv|fail|timeout)', "DNS resolution failure"),
        (r'(?i)(?:rate|limit|throttl)', "Rate limit exceeded"),
        (r'(?i)memory|oom|out of memory', "Out of memory error"),
        (r'(?i)timeout|timed out', "Service timeout"),
        (r'(?i)auth|unauthorized|forbidden', "Authentication/authorization failure"),
        (r'(?i)certif|cert|ssl|tls', "SSL/TLS certificate error"),
        (r'(?i)disk|storage|space', "Disk space exhausted"),
        (r'(?i)network|connect.*refused', "Network connection refused"),
        (r'(?i)null.*pointer|attribute.*error', "Null pointer exception"),
    ]

    root_cause = "Unknown error"
    for pattern, rc in rc_patterns:
        if re.search(pattern, cleaned_log):
            root_cause = rc
            break

    parser = ResponseParser()
    diagnosis_text = (
        f"ROOT CAUSE: {root_cause}\n"
        f"CONFIDENCE: High\n"
        f"FIX STEPS:\n"
        f"1. Investigate the {root_cause.lower()}\n"
        f"2. Apply the appropriate fix\n"
        f"3. Monitor the service\n"
        f"NOTES: This issue was identified and resolved.\n"
    )
    diagnosis = parser.parse_diagnosis(diagnosis_text)

    return {
        'incident_id': f"INC-{int(time.time()) % 100000:05d}",
        'diagnosis': diagnosis,
        'incident_type': 'NOVEL',
        'similarity_score': 0.0,
        'model_used': 'simulation',
        'model_tier': 'offline',
        'routing_reason': 'Offline mode (simulated)',
        'cost_usd': 0.0,
        'latency_seconds': 0.5,
    }

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    # Pre-load demo data
    load_demo_incidents()
    logger.info(f"Loaded {len(_demo_incidents)} demo incidents")
    yield

app = FastAPI(
    title="Incident Response Agent API",
    description="AI-powered SRE assistant with auto-remediation",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "demo_incidents": len(_demo_incidents)}


@app.post("/api/diagnose", response_model=DiagnoseResponse)
async def diagnose(req: DiagnoseRequest):
    """Diagnose an error log and return structured result."""
    try:
        if req.use_llm and os.getenv('GROQ_API_KEY'):
            engine = get_inference_engine()
            result = engine.diagnose(req.error_log)
        else:
            result = simulate_diagnosis(req.error_log)

        diagnosis = result.get('diagnosis', {})

        return DiagnoseResponse(
            incident_id=result.get('incident_id', 'UNKNOWN'),
            incident_type=result.get('incident_type', 'NOVEL'),
            similarity_score=result.get('similarity_score', 0.0),
            root_cause=diagnosis.get('root_cause', 'Unknown'),
            confidence=diagnosis.get('confidence', 'Medium'),
            fix_steps=diagnosis.get('fix_steps', []),
            notes=diagnosis.get('notes', ''),
            model_used=result.get('model_used', 'unknown'),
            model_tier=result.get('model_tier', 'unknown'),
            cost_usd=result.get('cost_usd', 0.0),
            latency_seconds=result.get('latency_seconds', 0.0),
            routing_reason=result.get('routing_reason', ''),
        )

    except Exception as e:
        logger.exception("Diagnosis failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/remediate/plan")
async def remediate_plan(req: RemediateRequest):
    """Generate a remediation plan from diagnosis result."""
    try:
        diagnosis_result = {
            'incident_id': req.incident_id,
            'incident_type': req.incident_type,
            'diagnosis': {
                'root_cause': req.root_cause,
                'fix_steps': req.fix_steps,
                'confidence': 'High',
                'notes': '',
            },
            'extracted_fields': {
                'service': 'unknown',
                'error_type': 'unknown',
            },
        }

        engine = get_remediation_engine()
        plan = engine.plan(diagnosis_result)

        return PlanResponse(
            incident_id=plan.incident_id,
            branch_name=plan.branch_name,
            pr_title=plan.pr_title,
            tasks=[
                TaskResponse(
                    id=t.id,
                    description=t.description,
                    change_type=t.change_type.value,
                    file_path=t.file_path,
                    status=t.status.value,
                    priority=t.priority,
                )
                for t in plan.tasks
            ],
            summary=plan.summary,
        )

    except Exception as e:
        logger.exception("Remediation plan failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/remediate/run")
async def remediate_run(req: RemediateRequest):
    """Run the full remediation pipeline and stream progress via SSE."""
    diagnosis_result = {
        'incident_id': req.incident_id,
        'incident_type': req.incident_type,
        'diagnosis': {
            'root_cause': req.root_cause,
            'fix_steps': req.fix_steps,
            'confidence': 'High',
            'notes': '',
        },
        'extracted_fields': {
            'service': 'unknown',
            'error_type': 'unknown',
        },
    }

    async def event_stream():
        engine = get_remediation_engine()

        # Step 5: Plan
        yield {"event": "step", "data": json.dumps({"step": 5, "name": "Generating fix tasks...", "progress": 20})}
        try:
            plan = engine.plan(diagnosis_result)
            plan_data = PlanResponse(
                incident_id=plan.incident_id,
                branch_name=plan.branch_name,
                pr_title=plan.pr_title,
                tasks=[
                    TaskResponse(
                        id=t.id, description=t.description,
                        change_type=t.change_type.value, file_path=t.file_path,
                        status=t.status.value, priority=t.priority,
                    ) for t in plan.tasks
                ],
                summary=plan.summary,
            )
            yield {"event": "plan", "data": plan_data.model_dump_json()}

            if not plan.tasks:
                yield {"event": "error", "data": json.dumps({"error": "No fix tasks generated"})}
                return
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
            return

        # Steps 6-7: Apply fixes + tests
        yield {"event": "step", "data": json.dumps({"step": 6, "name": "Applying fixes and generating tests...", "progress": 40})}
        try:
            all_applied = engine.apply(plan)
            applied = len([t for t in plan.tasks if t.status.value == "applied"])
            failed = len([t for t in plan.tasks if t.status.value == "failed"])
            test_tasks = len([t for t in plan.tasks if t.id.startswith('test-')])
            yield {"event": "apply", "data": json.dumps({
                "success": all_applied, "applied": applied,
                "failed": failed, "test_tasks_generated": test_tasks,
            })}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": f"Apply failed: {e}"})}
            return

        # Step 8: Validate
        yield {"event": "step", "data": json.dumps({"step": 8, "name": "Running validation tests...", "progress": 60})}
        try:
            validation = engine.validate(plan)
            yield {"event": "validate", "data": json.dumps({
                "passed": validation.passed,
                "total_tests": validation.total_tests,
                "passed_tests": validation.passed_tests,
                "failed_tests": validation.failed_tests,
                "errors": validation.errors,
                "output": validation.output,
            })}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": f"Validation failed: {e}"})}
            return

        # Steps 9-10: PR
        yield {"event": "step", "data": json.dumps({"step": 9, "name": "Creating PR...", "progress": 80})}
        try:
            pr = engine.create_pr(plan)
            yield {"event": "pr", "data": json.dumps({
                "success": pr.success,
                "branch_url": pr.branch_url,
                "pr_url": pr.pr_url,
                "pr_number": pr.pr_number,
                "error": pr.error,
            })}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": f"PR creation failed: {e}"})}
            return

        # Done
        yield {"event": "complete", "data": json.dumps({"progress": 100})}

    return EventSourceResponse(event_stream())


@app.get("/api/demo/presets")
async def demo_presets():
    """Get preset demo incidents for quick testing."""
    incidents = load_demo_incidents()
    # Return last 3 for demo
    presets = []
    for inc in incidents[-3:]:
        presets.append({
            "id": inc.get("id", "INC-???"),
            "title": inc.get("root_cause", "Unknown")[:80],
            "error_log": inc.get("raw_log", "")[:500],
            "service": inc.get("service", "unknown"),
        })
    return {"presets": presets}


@app.get("/api/history")
async def get_history():
    """Get incident history from memory."""
    try:
        engine = get_inference_engine()
        vector_store = engine.retriever.vector_store
        all_incidents = vector_store.get_all()

        history = []
        for inc in all_incidents:
            meta = inc.get('metadata', {})
            history.append(HistoryEntry(
                incident_id=meta.get('incident_id', 'N/A'),
                incident_type=meta.get('incident_type', 'UNKNOWN'),
                root_cause=meta.get('root_cause', 'N/A')[:80],
                service=meta.get('service', 'N/A'),
                fix_applied=meta.get('fix_applied', 'N/A')[:80],
                resolution_time_minutes=meta.get('resolution_time_minutes', 0),
                model_used=meta.get('model_used', 'N/A')[:30],
                cost_usd=meta.get('cost_usd', 0.0),
                timestamp=meta.get('timestamp', ''),
            ))

        return {"incidents": history, "total": len(history)}

    except Exception as e:
        logger.exception("Failed to get history")
        return {"incidents": [], "total": 0, "error": str(e)}


@app.get("/api/audit")
async def get_audit():
    """Get full audit trail."""
    try:
        audit = get_audit_logger()
        entries = audit.get_all()

        audit_entries = []
        for e in entries:
            audit_entries.append(AuditEntry(
                incident_id=e.get('incident_id', 'N/A'),
                incident_type=e.get('incident_type', 'N/A'),
                root_cause=e.get('root_cause', 'N/A')[:60],
                model_used=e.get('model_used', 'N/A'),
                cost_usd=e.get('cost_usd', 0.0),
                latency_seconds=e.get('latency_seconds', 0.0),
                timestamp=e.get('timestamp', ''),
                resolved=e.get('resolved', False),
            ))

        stats = audit.get_stats() if hasattr(audit, 'get_stats') else {}

        return {
            "entries": audit_entries,
            "total": len(audit_entries),
            "stats": {
                "total_cost": stats.get('total_cost', 0.0),
                "avg_cost": stats.get('avg_cost', 0.0),
                "avg_latency": stats.get('avg_latency', 0.0),
            },
        }

    except Exception as e:
        logger.exception("Failed to get audit")
        return {"entries": [], "total": 0, "stats": {}, "error": str(e)}


# ---------------------------------------------------------------------------
# Serve React static files in production
# ---------------------------------------------------------------------------

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
