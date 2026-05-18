# 🛡️ Incident Response Agent

**AI-powered SRE assistant that diagnoses system failures from error logs and gets smarter over time by remembering past incidents.**

Built for DevOps/engineering teams who need fast, cost-effective incident diagnosis. Uses **Hindsight** for persistent memory (so it learns from every resolved incident) and **cascadeflow** for intelligent model routing (so known incidents use cheap models and novel incidents use powerful ones).

---

## Architecture

```
                         ┌─────────────────────┐
                         │    User (CLI)        │
                         │  python main.py      │
                         └──────────┬──────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────┐
│                    Inference Engine                       │
│                                                          │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Preprocessor│─►│   Retriever  │─►│  Model Router    │ │
│  │ (clean log) │  │ (find past)  │  │ (cascadeflow)    │ │
│  └────────────┘  └──────┬───────┘  └────────┬────────┘ │
│                         │                    │          │
│                         ▼                    ▼          │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │  Indexer   │◄─│  Response    │◄─│  Prompt Builder  │ │
│  │ (store fix)│  │  Parser      │  │  (template)      │ │
│  └────────────┘  └──────────────┘  └─────────────────┘ │
└──────────────────────────┬───────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Hindsight  │  │    Groq API  │  │   Ollama     │
│  (memory)    │  │ (LLM Cloud)  │  │ (Local Fallb)│
│  or local    │  │  cheap/power │  │  $0 cost     │
│  JSON store  │  │  ~$0-0.03   │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## Features

- **🔍 Intelligent Diagnosis**: Paste any error log and get a structured diagnosis with root cause, confidence level, and fix steps
- **🧠 Persistent Memory**: Uses Hindsight (or local JSON fallback) to remember past incidents and their fixes
- **💰 Cost-Optimized Routing**: cascadeflow automatically routes known incidents to cheap models ($0.001) and novel incidents to powerful ones ($0.031)
- **🚨 Budget Caps**: Automatically switches to local Ollama when budget limit is hit
- **📊 Audit Trail**: Full transparency with cost tracking, latency monitoring, and incident history
- **🔌 Offline Mode**: Works entirely offline with local file store — no API keys required for the demo

---

## How Hindsight Memory Works

Hindsight is a persistent memory layer that stores resolved incidents as vector embeddings. When a new incident comes in:

1. The error log is cleaned and embedded into a vector
2. Hindsight searches for similar past incidents using cosine similarity
3. If similarity >= 0.8 → **KNOWN** incident (use cheap model)
4. If similarity 0.5-0.8 → **PARTIAL MATCH** (use cheap model with verification note)
5. If similarity < 0.5 → **NOVEL** incident (use powerful model)

When an engineer marks an incident as resolved, it's stored back into Hindsight with the root cause, fix applied, service, and resolution time. Over time, the agent gets smarter and cheaper.

**No Hindsight API key?** The system automatically falls back to a local JSON file store (`data/vectordb/memory_store.json`) with keyword-based similarity search.

---

## How cascadeflow Routing Works

cascadeflow provides intelligent model routing based on:

| Incident Type | Similarity | Model | Cost per call |
|---|---|---|---|
| KNOWN | >= 0.8 | `groq/llama-3.1-8b-instant` | ~$0.001 |
| PARTIAL | 0.5 - 0.8 | `groq/llama-3.1-8b-instant` | ~$0.001 |
| NOVEL | < 0.5 | `groq/qwen/qwen3-32b` | ~$0.031 |
| Budget Exhausted | any | `ollama/llama3` (local) | $0.00 |

**Cost comparison (before vs after):**

| Scenario | Before (no memory) | After (with memory) |
|---|---|---|
| 10 incidents (8 known, 2 novel) | $0.31 (10 × $0.031) | $0.07 (8 × $0.001 + 2 × $0.031) |
| Savings | — | **~77%** |

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Groq API key (free): https://console.groq.com/keys
- Hindsight API key (optional, get $50 free with `MEMHACK515`): https://ui.hindsight.vectorize.io
- Ollama (optional, for local fallback): https://ollama.ai

### 2. Install

```bash
# Clone the repo
cd incident-agent

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env — set your GROQ_API_KEY for live mode
# (the offline demo works without any API keys)
```

### 3. Run the Demo (Offline — No API Keys Needed)

```bash
python main.py demo-offline
```

This runs a complete simulation showing:
- How the agent diagnoses incidents
- How memory matching makes subsequent diagnoses cheaper
- The audit trail with cost tracking

### 4. Run the Live Demo (Requires GROQ_API_KEY)

```bash
python main.py demo
```

### 5. Diagnose a Real Incident

```bash
python main.py diagnose
```

Paste your error log and press Ctrl+D (or type END on a new line).

---

## CLI Commands

| Command | Description |
|---|---|
| `python main.py diagnose` | Paste an error log and get structured diagnosis |
| `python main.py resolve` | Mark last incident as resolved (stores in memory) |
| `python main.py history` | Show all past incidents stored in memory |
| `python main.py audit` | Show full audit trail with costs and latency |
| `python main.py demo` | Run automated demo with synthetic data (requires API key) |
| `python main.py demo-offline` | Run demo without API calls (simulated) |

---

## Example Output

```
┌─────────────────────────────────────────────────────────────────┐
│                    INCIDENT DIAGNOSIS #INC-011                   │
├─────────────────────────────────────────────────────────────────┤
│ Status    : ⚡ KNOWN INCIDENT (memory match)                     │
│ Incident ID: INC-011                                            │
│ Similarity : 95.00%                                             │
│ Model      : llama3-8b-8192 (cheap)                             │
│ Cost       : $0.001000                                          │
│ Latency    : 0.9s                                               │
│                                                                 │
│ KNOWN incident (similarity=0.95) - using cheap model            │
│                                                                 │
│ ROOT CAUSE: Redis connection pool exhausted due to payment spike│
│ CONFIDENCE: High                                                │
│                                                                 │
│ FIX STEPS:                                                      │
│   1. Set CONNECTION_POOL_SIZE=25 in ConfigMap                   │
│   2. kubectl rollout restart deploy/payment-processor-v2        │
│   3. Monitor redis-03 connections for 5 minutes                 │
│                                                                 │
│ NOTES: This exact issue occurred on INC-003. Resolution took 8  │
│ minutes last time.                                              │
│                                                                 │
│ Past incidents in context:                                      │
│   • Redis connection pool exhausted (sim: 95%)                  │
│   • Redis pool timeout (sim: 82%)                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
incident-agent/
├── config/
│   ├── model_config.yaml         # Model definitions & routing config
│   └── logging_config.yaml       # Logging configuration
├── data/
│   ├── cache/                    # Cached data
│   ├── embeddings/               # Pre-computed embeddings
│   ├── vectordb/                 # Local memory store
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
│   ├── rag/                      # Retrieval-Augmented Generation
│   │   ├── vector_store.py       # Hindsight/local memory wrapper
│   │   ├── embedder.py           # Log-to-embedding conversion
│   │   ├── retriever.py          # Memory search & classification
│   │   └── indexer.py            # Store resolved incidents
│   ├── processing/               # Input processing pipeline
│   │   ├── preprocessor.py       # Log cleaning & field extraction
│   │   ├── tokenizer.py          # Token counting & cost estimation
│   │   └── chunking.py           # Large log splitting
│   └── inference/
│       ├── inference_engine.py   # Main agent loop
│       └── response_parser.py    # Structured output parsing
├── tests/                        # Unit & integration tests
├── scripts/                      # Utility scripts
├── main.py                       # CLI entry point
├── audit_log.py                  # Audit trail display
├── logging_config.py             # Logging setup
├── .env.example                  # Environment variables template
├── Dockerfile                    # Container build
├── docker-compose.yml            # Multi-service setup
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## Error Handling

The agent handles these scenarios gracefully:

| Scenario | Behavior |
|---|---|
| Groq API rate limit | Retries with exponential backoff (max 3 retries) |
| Hindsight connection failure | Warns and proceeds with local JSON store |
| Budget cap reached | Switches to Ollama, logs the switch |
| Ollama not running | Asks user to start it, offers to proceed with powerful model |
| Empty/too-short input | Asks user to provide more detail |
| Hindsight returns zero matches | Proceeds as NOVEL incident |
| Malformed model response | Retries once, then returns raw response |

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `GROQ_API_KEY` | — | Yes* | Groq API key for LLM calls |
| `HINDSIGHT_API_KEY` | — | No | Hindsight API key for persistent memory |
| `HINDSIGHT_BASE_URL` | `https://api.hindsight.vectorize.io` | No | Hindsight API base URL |
| `HINDSIGHT_PIPELINE_ID` | `incident-memory-bank` | No | Hindsight pipeline/bank ID |
| `BUDGET_CAP_USD` | `1.00` | No | Maximum spend before switching to Ollama |
| `CHEAP_MODEL` | `groq/llama-3.1-8b-instant` | No | Model for known/partial incidents |
| `POWERFUL_MODEL` | `groq/qwen/qwen3-32b` | No | Model for novel incidents |
| `LOCAL_MODEL` | `ollama/llama3` | No | Ollama model for budget fallback |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | No | Ollama server URL |

*\* Required for live API calls. Offline demo mode works without it.*

---

## Docker

```bash
# Build and run
docker build -t incident-agent .
docker run -it --env-file .env incident-agent python main.py diagnose

# Or with docker-compose (with Ollama for local fallback)
docker compose --profile local up -d
docker compose exec incident-agent python main.py diagnose
```

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run unit tests only
python -m pytest tests/unit/ -v

# Run integration tests (requires API keys)
python -m pytest tests/integration/ -v

# Check import compatibility
python scripts/run_tests.sh
```

---

## License

MIT
