# 🛡️ Incident Response Agent

**AI-powered SRE assistant that diagnoses system failures from error logs, auto-remediates with tested fixes, and pushes PR-ready code to GitHub — getting smarter over time by remembering past incidents.**

Built for DevOps/engineering teams who need fast, cost-effective incident response. Uses **Hindsight** for persistent memory (so it learns from every resolved incident) and **cascadeflow** for intelligent model routing (so known incidents use cheap models and novel incidents use powerful ones).

---

## The Full Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                    1.  Detect  ◄──  Error log (any format)          │
│                    2.  Analyze ◄──  Log + codebase context          │
│                    3.  Diagnose ◄──  Root cause + fix steps         │
│                    4.  Plan     ◄──  Generate fix tasks             │
│                    5.  Fix      ◄──  Apply config/code changes      │
│                    6.  Test     ◄──  Generate + run validation      │
│                    7.  Commit   ◄──  Git branch with all changes    │
│                    8.  Push     ◄──  GitHub branch + PR 🚀          │
└─────────────────────────────────────────────────────────────────────┘
```

### One Command Does It All

```bash
python main.py remediate          # Steps 4–8: plan → fix → test → commit → push
python main.py remediate-demo     # Same, using synthetic PayStream incidents
```

### Or Step by Step

```bash
python main.py diagnose           # Steps 1–3: log → analysis → root cause
python main.py remediate-plan     # Preview fix tasks before applying
python main.py remediate          # Apply fixes, run tests, create PR
```

---

## Architecture

```
                         ┌─────────────────────┐
                         │    User (CLI)        │
                         │  python main.py      │
                         └──────────┬──────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         Inference Engine                              │
│                                                                      │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ Preprocessor│─►│  Retriever   │─►│ Model Router │─►│  LLM      │ │
│  │ (clean log) │  │ (find past)  │  │(cascadeflow) │  │  (Groq)   │ │
│  └────────────┘  └──────┬───────┘  └──────────────┘  └───────────┘ │
│                         │                                           │
│                         ▼                                           │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────────────────────┐ │
│  │  Indexer   │◄─│  Response    │◄─│  Prompt Builder + Parser    │ │
│  │ (store fix)│  │  Parser      │  │                             │ │
│  └────────────┘  └──────────────┘  └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌──────────────┐          ┌──────────────┐          ┌──────────────────┐
│   Hindsight  │          │    Groq API  │          │  Ollama (Local)  │
│  (memory)    │          │  (LLM Cloud) │          │  $0 cost fallback│
│  or local    │          │  $0.001-0.03 │          │                  │
│  JSON store  │          │  per call    │          │                  │
└──────────────┘          └──────────────┘          └──────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       Remediation Engine                             │
│                                                                      │
│  ┌──────────────┐  ┌──────────┐  ┌────────────┐  ┌───────────────┐ │
│  │Task Generator│─►│  Fixer   │─►│Test Gen.   │─►│  Validator    │ │
│  │(rules + LLM) │  │(k8s/code)│  │(pytest)    │  │(8+ tests)     │ │
│  └──────────────┘  └──────────┘  └────────────┘  └───────┬───────┘ │
│                                                           │         │
│  ┌──────────────┐  ┌──────────────┐                      │         │
│  │GitHub Pusher │◄─│Local Git     │◄─────────────────────┘         │
│  │(gh CLI/API)  │  │(fixes repo)  │  ┌──────────────────────────┐  │
│  └──────┬───────┘  └──────────────┘  │  PR created with all     │  │
│         │                            │  fixes + passing tests!  │  │
│         └────────────────────────────►  github.com/user/repo/pull│  │
│                                       └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Features

- **🔍 Intelligent Diagnosis**: Paste any error log and get structured diagnosis with root cause, confidence, and fix steps
- **🧠 Persistent Memory**: Uses Hindsight (or local JSON fallback) to remember past incidents and their fixes
- **💰 Cost-Optimized Routing**: cascadeflow routes known incidents to cheap models (~$0.001) and novel ones to powerful models (~$0.031)
- **🚨 Budget Caps**: Auto-switches to local Ollama when budget limit is hit
- **🛠️ Auto-Remediation**: Generates fix tasks, applies config/code changes, runs tests, and creates PR-ready branches
- **🔗 GitHub Integration**: Pushes fix branches and creates Pull Requests automatically via `gh` CLI or REST API
- **📊 Audit Trail**: Full transparency with cost tracking, latency monitoring, and incident history
- **🌐 Web App**: Browser-based UI with real-time diagnosis, cost charts, and remediation pipeline progress
- **🔌 Offline Mode**: Works entirely offline with local file store — no API keys required for the demo

---

## How Hindsight Memory Works

Hindsight is a persistent memory layer that stores resolved incidents as vector embeddings. When a new incident comes in:

1. The error log is cleaned and embedded into a vector
2. Hindsight searches for similar past incidents using cosine similarity
3. If similarity >= 0.8 → **KNOWN** incident (use cheap model)
4. If similarity 0.5–0.8 → **PARTIAL MATCH** (use cheap model with verification)
5. If similarity < 0.5 → **NOVEL** incident (use powerful model)

When an incident is resolved, it's stored back into Hindsight with root cause, fix applied, service, and resolution time. Over time, the agent gets smarter and cheaper.

**No Hindsight API key?** Falls back to a local JSON file store (`data/memory_store.json`) with keyword-based similarity search.

---

## How cascadeflow Routing Works

| Incident Type | Similarity | Model | Cost per call |
|---|---|---|---|
| KNOWN | >= 0.8 | `groq/llama-3.1-8b-instant` | ~$0.001 |
| PARTIAL | 0.5 – 0.8 | `groq/llama-3.1-8b-instant` | ~$0.001 |
| NOVEL | < 0.5 | `groq/qwen/qwen3-32b` | ~$0.031 |
| Budget Exhausted | any | `ollama/llama3` (local) | $0.00 |

**Cost savings example:**

| Scenario | Before (no memory) | After (with memory) |
|---|---|---|
| 10 incidents (8 known, 2 novel) | $0.31 (10 × $0.031) | $0.07 (8 × $0.001 + 2 × $0.031) |
| Savings | — | **~77%** |

---

## How Auto-Remediation Works

When you run `python main.py remediate`, the Remediation Engine executes steps 4–8:

| Step | Component | What It Does |
|---|---|---|
| 4. **Plan** | `TaskGenerator` | Maps fix steps to 5 action types: `config_edit`, `code_edit`, `file_create`, `k8s_manifest`, `script_run` |
| 5. **Fix** | `Fixer` | Applies changes to the target repo (`fixes/paystream/`): edits YAML configs, k8s manifests, or runs kubectl commands |
| 6. **Test** | `TestGenerator` | Generates pytest files tailored to each fix (network policy tests, config validation, pool health checks) |
| 7. **Validate** | `Validator` | Runs 8+ validation tests and reports pass/fail |
| 8. **Push** | `GitHubPusher` | Commits to a feature branch and creates a Pull Request via `gh` CLI (or REST API, or git push fallback) |

### Fix Task Types

| Type | Description | Example |
|---|---|---|
| `config_edit` | Modify YAML/JSON config files | Update rate limit, pool size, timeout |
| `code_edit` | Modify source code files | Fix connection leak, add retry logic |
| `file_create` | Create new config or test files | Add network policy, generate test |
| `k8s_manifest` | Update Kubernetes deployment YAMLs | Scale replicas, add probes, update env |
| `script_run` | Execute a shell command | `kubectl scale deployment`, `restart pod` |

---

## Quick Start

### 1. Prerequisites

- **Python 3.11+**
- **Groq API key** (free): https://console.groq.com/keys
- **Hindsight API key** (optional): https://ui.hindsight.vectorize.io
- **Ollama** (optional, for local fallback): https://ollama.ai
- **GitHub CLI** (optional, for PR creation): `winget install GitHub.cli`

### 2. Install

```bash
# Clone the repo
cd incident-agent

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env — set your GROQ_API_KEY for live mode
```

### 3. Run the Demo (Offline — No API Keys)

```bash
python main.py demo-offline
```

### 4. Run the Full Remediation Demo

```bash
python main.py remediate-demo
```

This runs the entire pipeline on 3 synthetic PayStream incidents, applies fixes, runs tests, commits, and pushes PRs to GitHub.

### 5. Diagnose a Real Incident

```bash
python main.py diagnose
```

Paste your error log and press Ctrl+D (or type END on a new line).

---

## CLI Commands

| Command | Description |
|---|---|
| **Diagnosis & Memory** |
| `python main.py diagnose` | Paste an error log and get structured diagnosis |
| `python main.py diagnose-mock` | Offline simulated diagnosis (no API calls) |
| `python main.py resolve` | Mark last incident as resolved (stores in memory) |
| `python main.py history` | Show all past incidents stored in memory |
| `python main.py audit` | Show full audit trail with costs and latency |
| **Demo** |
| `python main.py demo` | Run automated diagnosis demo (requires API key) |
| `python main.py demo-offline` | Run diagnosis demo without API calls |
| **Remediation** |
| `python main.py remediate` | Full pipeline: plan → fix → test → PR → push |
| `python main.py remediate-plan` | Show remediation plan without applying changes |
| `python main.py remediate-demo` | Demo auto-remediation on synthetic incidents |

---

## GitHub Integration

The `GitHubPusher` supports 3 methods in priority order:

| Method | Requires | Status |
|---|---|---|
| `gh` CLI | `gh` installed + authenticated | ✅ Creates PRs automatically |
| REST API | PAT with `Contents: write` + `Pull requests: write` | ✅ Creates PRs automatically |
| Git Push | Any auth method | ✅ Pushes branches + provides PR URLs |

### Setup

```bash
# 1. Install GitHub CLI
winget install GitHub.cli

# 2. Authenticate with your PAT
echo $GITHUB_TOKEN | gh auth login --with-token

# 3. Or set in .env
GITHUB_TOKEN=github_pat_...
GITHUB_REPO_OWNER=your-username
GITHUB_REPO_NAME=paystream-infra
```

The **fine-grained PAT needs** these permissions on the target repo:
- **Contents**: Read and write
- **Pull requests**: Read and write
- **Metadata**: Read (auto-granted)

---

## Web App

The project includes a browser-based UI built with FastAPI (backend) and React/Vite (frontend).

```bash
# Start both servers
bash start.sh

# Or manually:
# Backend:  http://localhost:8000
cd backend && uvicorn main:app --reload --port 8000

# Frontend: http://localhost:5173
cd frontend && npm run dev
```

---

## Example Diagnosis Output

```
┌─────────────────────────────────────────────────────────────────┐
│                    INCIDENT DIAGNOSIS #2993b24e                  │
├─────────────────────────────────────────────────────────────────┤
│ Status    : [?] PARTIAL MATCH (verify suggested)                │
│ Incident ID: 2993b24e                                           │
│ Similarity: 50.00%                                              │
│ Model      : llama-3.1-8b-instant (cheap)                      │
│ Cost       : $0.000040                                          │
│ Latency    : 1.6s                                               │
│                                                                 │
│ PARTIAL incident (similarity=0.50) - using cheap model          │
│                                                                 │
│ ROOT CAUSE: auth-service rate limit exceeded on JWT             │
│ token generation endpoint — possible brute force attack         │
│                                                                 │
│ CONFIDENCE: High                                                │
│                                                                 │
│ FIX STEPS:                                                      │
│   1. Review/adjust auth-service rate limiting config            │
│   2. Implement Leaky Bucket algorithm for brute force           │
│   3. Add IP blocking + user-ID based rate limiting              │
│                                                                 │
│ Past incidents in context:                                      │
│   • JWT token expiry (sim: 50%)                                 │
│   • JWT token validation failure (sim: 50%)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Example Remediation Result

```
┌────────────────── REMEDIATION RESULT ──────────────────┐
│                                                         │
│  Tasks: 1 total                                         │
│    Applied: 1                                           │
│                                                         │
│  Validation: PASSED                                     │
│    8/8 tests passed                                     │
│                                                         │
│  Pull Request: Created 🎉                               │
│    URL: https://github.com/user/repo/pull/4              │
│                                                         │
│  Changes applied in: fixes/paystream/                   │
│    → k8s/network-policies/restrict-payment-access.yaml  │
│      (IP blocking + rate limiting)                      │
└─────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
incident-agent/
├── config/
│   ├── model_config.yaml         # Model definitions & routing config
│   └── logging_config.yaml       # Logging configuration
├── data/
│   ├── memory_store.json         # Local incident memory store
│   └── demo_incidents.json       # 15 synthetic PayStream incidents
├── src/
│   ├── core/                     # LLM clients & model routing
│   │   ├── base_llm.py           # Abstract LLM interface
│   │   ├── groq_client.py        # Groq API wrapper (with retry)
│   │   ├── local_llm.py          # Ollama fallback client
│   │   └── model_factory.py      # cascadeflow routing logic
│   ├── prompts/
│   │   ├── templates.py          # Diagnosis prompt templates
│   │   └── chain.py              # Multi-step reasoning chain
│   ├── processing/
│   │   ├── preprocessor.py       # Log cleaning & field extraction
│   │   ├── tokenizer.py          # Token counting & cost estimation
│   │   └── chunking.py           # Large log splitting
│   ├── rag/
│   │   ├── vector_store.py       # Hindsight/local memory wrapper
│   │   ├── embedder.py           # Log-to-embedding conversion
│   │   ├── retriever.py          # Memory search & classification
│   │   └── indexer.py            # Store resolved incidents
│   ├── inference/
│   │   ├── inference_engine.py   # Main agent loop
│   │   └── response_parser.py    # Structured output parsing
│   └── remediation/              # Auto-remediation pipeline
│       ├── engine.py             # Orchestrates steps 4–8
│       ├── task_generator.py     # Maps fix steps to actionable tasks
│       ├── fixer.py              # Applies config/code/k8s changes
│       ├── test_generator.py     # Generates pytest validation files
│       ├── validator.py          # Runs tests and reports results
│       ├── github_pusher.py      # Git commit + GitHub PR creation
│       └── models.py             # Data models (FixTask, FixPlan, etc.)
├── backend/                      # FastAPI web backend
│   ├── main.py                   # API endpoints: diagnose, history, etc.
│   └── fixes/paystream/          # PayStream demo infra config
├── frontend/                     # React + Vite web frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── IncidentTable.tsx
│   │   │   ├── DiagnosisPanel.tsx
│   │   │   ├── PipelineProgress.tsx
│   │   │   └── CostChart.tsx
│   │   └── services/api.ts
│   └── index.html
├── fixes/paystream/              # Target repo for auto-remediation
│   ├── configs/                  # Service configs (Redis, Postgres, etc.)
│   ├── k8s/                      # Kubernetes manifests
│   ├── src/                      # Service source code
│   └── tests/                    # Validation test suites
├── tests/
│   ├── unit/                     # Unit tests (LLM, prompts, remediation)
│   └── integration/              # Integration tests (API, end-to-end)
├── main.py                       # CLI entry point
├── audit_log.py                  # Audit trail display
├── logging_config.py             # Logging setup
├── start.sh                      # Web app launcher
├── pytest.ini                    # Test configuration
├── Dockerfile                    # Container build
├── docker-compose.yml            # Multi-service setup
└── requirements.txt              # Python dependencies
```

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `GROQ_API_KEY` | — | Yes* | Groq API key for LLM calls |
| `HINDSIGHT_API_KEY` | — | No | Hindsight API key for vector memory |
| `HINDSIGHT_BASE_URL` | `https://api.hindsight.vectorize.io` | No | Hindsight API base URL |
| `HINDSIGHT_PIPELINE_ID` | `incident-memory-bank` | No | Hindsight pipeline/bank ID |
| `GITHUB_TOKEN` | — | No | GitHub PAT for PR creation |
| `GITHUB_REPO_OWNER` | — | No | GitHub username/org for fixes repo |
| `GITHUB_REPO_NAME` | `paystream-infra` | No | GitHub repo name for fixes |
| `BUDGET_CAP_USD` | `1.00` | No | Max spend before Ollama fallback |
| `CHEAP_MODEL` | `groq/llama-3.1-8b-instant` | No | Model for known/partial incidents |
| `POWERFUL_MODEL` | `groq/qwen/qwen3-32b` | No | Model for novel incidents |
| `LOCAL_MODEL` | `ollama/llama3` | No | Ollama model for budget fallback |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | No | Ollama server URL |

*\* Required for live API calls. Offline demo mode works without it.*

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# Remediation-specific tests
python -m pytest tests/unit/test_remediation_*.py -v

# Integration tests (requires API keys)
python -m pytest tests/integration/ -v
```

---

## Docker

```bash
# Build and run CLI
docker build -t incident-agent .
docker run -it --env-file .env incident-agent python main.py diagnose

# With docker-compose (includes Ollama for local fallback)
docker compose --profile local up -d
docker compose exec incident-agent python main.py diagnose
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Groq API rate limit | Retries with exponential backoff (max 3 retries) |
| Hindsight connection failure | Warns and proceeds with local JSON store |
| Budget cap reached | Switches to Ollama, logs the switch |
| Ollama not running | Asks user to start it, offers to proceed with powerful model |
| Empty/too-short input | Asks user to provide more detail |
| Hindsight returns zero matches | Proceeds as NOVEL incident |
| GitHub API push fails | Falls back to git push + PR URL generation |
| `gh` CLI not available | Falls back to REST API, then git push |

---

## License

MIT
