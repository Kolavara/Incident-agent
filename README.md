# 🛡️ Incident-agent

**AI-powered SRE assistant** that diagnoses system failures from logs, auto-remediates with tested code, and opens PRs on GitHub—getting smarter (and more cost-efficient) with every incident.

[![Build Status](https://img.shields.io/github/actions/workflow/status/Kolavara/Incident-agent/ci.yml?branch=main)](https://github.com/Kolavara/Incident-agent/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Open Issues](https://img.shields.io/github/issues/Kolavara/Incident-agent)](https://github.com/Kolavara/Incident-agent/issues)
[![Stars](https://img.shields.io/github/stars/Kolavara/Incident-agent.svg?style=social)](https://github.com/Kolavara/Incident-agent)

---

## 🚦 Features

- **AI diagnosis**: Paste any error log and get structured, root-cause analysis and fix steps.
- **Automated remediation**: Generates, applies, tests, and PRs fixes for configs, code, Kubernetes, and more.
- **Persistent memory**: Uses vector store (Hindsight) to recognize and reapply past fixes—gets faster and cheaper.
- **Cost-optimized LLM routing**: Cascadeflow smartly selects between powerful, cheap, and local LLMs.
- **Offline-ready**: Demo mode runs with zero API keys.
- **Full GitHub integration**: Branch/push/PR with `gh` CLI, API, or fallback to manual.
- **Beautiful Web UI & CLI**: Use from terminal or browser.
- **Transparency**: Track costs, validation, and incident audit logs.

---

## 🖼️ Visual Overview

<div align="center">
  <img src="assets/pipeline-diagram.png" width="75%" alt="Incident-agent pipeline"/>
  <br/>
  <em>Fig: Full incident diagnosis to remediation pipeline (add your image!)</em>
</div>

---

## ⏩ Quickstart

**Requirements:** Python 3.11+, [Groq API key](https://console.groq.com/keys), *(optional) Hindsight API key, Ollama for local LLM, GitHub CLI*

```bash
git clone https://github.com/Kolavara/Incident-agent.git
cd Incident-agent
pip install -r requirements.txt
cp .env.example .env   # Edit as needed
```

**Run Demo (offline):**
```bash
python main.py demo-offline
```

**Full End-to-End Remediation (with synthetic demo):**
```bash
python main.py remediate-demo
```

**Real incident diagnosis:**
```bash
python main.py diagnose
# Paste your error log and press Ctrl+D or END
```

---

## 💡 How It Works

Incident-agent follows this intelligent pipeline:

1. **Detect**: Accepts your error log in any format.
2. **Analyze**: Correlates error with codebase/configs.
3. **Diagnose**: AI finds root cause and prescribes fix.
4. **Plan**: Breaks fix into actionable tasks.
5. **Fix**: Applies code, config, or k8s changes.
6. **Test**: Autogenerates and runs validation tests.
7. **Commit & Push**: Branch, PR (via GitHub API/CLI).
8. **Memory**: Remembers the fix for next time.

<div align="center">
  <img src="assets/architecture-diagram.png" width="75%" alt="Agent architecture"/>
  <br/>
  <em>(Add here: architecture diagram, even a simple draw.io/Excalidraw)</em>
</div>

---

## 🌐 Web App

- Modern React/Vite frontend + FastAPI backend.
- Real-time diagnosis and cost/progress dashboards.

```bash
bash start.sh                        # or:
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev
# Web UI: http://localhost:5173
```

---

## 🐍 CLI Example Output

<details>
<summary>Diagnosis Output</summary>

```
INCIDENT DIAGNOSIS #2993b24e
Status     : PARTIAL MATCH (verify)
Root Cause : auth-service rate limit exceeded on JWT...
Fix Steps:
 1. Adjust rate limit
 2. Add Leaky Bucket
 3. Enhanced IP rate limiting
Cost       : $0.000040
Latency    : 1.6s
```
</details>

<details>
<summary>Remediation & PR Output</summary>

```
REMEDIATION RESULT
Tasks    : 1 total applied
Validation: PASSED (8/8 tests)
Pull Request: Created 🎉 https://github.com/user/repo/pull/4
Example fix: k8s/network-policies/restrict-payment-access.yaml
(IP blocking + rate limiting)
```
</details>

---

## 🛠️ Commands

| Command                           | Description                                     |
|------------------------------------|-------------------------------------------------|
| `python main.py diagnose`          | Analyze logs, diagnose root cause               |
| `python main.py remediate-plan`    | Preview planned fixes without applying          |
| `python main.py remediate`         | Full remediation, test, validation, PR          |
| `python main.py remediate-demo`    | End-to-end demo (synthetic incidents)           |
| `python main.py history`           | Show past incidents from memory                 |
| `python main.py audit`             | Full audit trail, cost/latency breakdowns       |
| `python main.py demo-offline`      | Run in total offline mode (no API keys needed)  |

---

## 🏗️ Project Structure

```
incident-agent/
├── src/                  # Core agents, LLM orchestration, remediation logic
├── backend/              # FastAPI backend (API, sample target repo)
├── frontend/             # React web interface
├── fixes/paystream/      # Synthetic target repo (for demo remediation)
├── tests/                # Unit/integration tests
├── config/, data/        # Model configs, memory stores
├── main.py               # CLI entry
```

---

## 🔧 Environment Variables

| Variable            | Required | Purpose                                    |
|---------------------|----------|--------------------------------------------|
| GROQ_API_KEY        | Yes      | LLM API                                    |
| HINDSIGHT_API_KEY   | No       | Persistent memory                         |
| GITHUB_TOKEN        | No       | PR creation, branch pushings               |
| [See .env.example for more...] |          |                                     |

---

## 🧪 Testing

```bash
python -m pytest tests/ -v                   # Run all tests
python -m pytest tests/unit/                 # Unit tests
python -m pytest tests/integration/          # Integration tests (API keys req'd)
```

---

## 🐳 Docker

```bash
docker build -t incident-agent .
docker run -it --env-file .env incident-agent python main.py remediate-demo
# or
docker compose --profile local up -d
docker compose exec incident-agent python main.py diagnose
```

---

## 🪄 How to Add Images

- Place images in `.github/assets/`, `/docs/img/`, or `/assets/`.
- Use syntax like:
  ```md
  ![Pipeline](assets/pipeline-diagram.png)
  ```
- Diagrams: Excalidraw, Mermaid, draw.io all work—just export to PNG/SVG.

---

## 📄 License

MIT

---

**Tame incidents in minutes. Automate, learn, save—and keep your team in flow.**

