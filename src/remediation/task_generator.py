"""Task generator — converts diagnosis fix steps into structured implementation tasks.

Uses a two-phase approach:
1. Rule-based mapping from known fix patterns to structured tasks
2. LLM-based fallback for novel/ambiguous fix steps

Phase 1 handles the 15 demo incidents deterministically. Phase 2 handles
arbitrary fix steps from any diagnosis.
"""

import re
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.remediation.models import ChangeType, FixStatus, FixTask
from src.core.model_factory import ModelRouter
from src.core.base_llm import BaseLLMClient

logger = logging.getLogger('incident_agent.remediation.task_generator')

# ──────────────────────────────────────────────
# Rule-based patterns for known fix steps
# These map common fix step patterns to file paths
# and change types in the simulated PayStream repo.
#
# IMPORTANT: Pattern order matters — first match wins.
# More specific patterns MUST come before generic ones.
# ──────────────────────────────────────────────

FIX_PATTERNS: List[Dict[str, Any]] = [
    # ── Connection leak in code (most specific — must come before postgres pattern) ──
    {
        'patterns': [
            r'(?i)(?:fix|close|releas).*?connection\s*(?:leak|pool)',
            r'(?i)connection\s*(?:leak|pool).*?(?:fix|close|releas|detect|health)',
            r'(?i)pool.*?health.*?check',
        ],
        'file_path': 'src/payment-service/RedisPoolManager.java',
        'change_type': ChangeType.CODE_EDIT,
        'transform': 'update_java_code',
    },
    # ── Circuit breaker specific (must come before API gateway pattern) ──
    {
        'patterns': [
            r'(?i)circuit.?breaker.*?(?:threshold|traffic|shed)',
        ],
        'file_path': 'configs/payment-processor/configmap.yaml',
        'change_type': ChangeType.CONFIG_EDIT,
        'transform': 'update_yaml_value',
    },
    # ── API gateway timeout (must come before generic timeout pattern) ──
    {
        'patterns': [
            r'(?i)(?:api.?gateway|upstream).*?(?:timeout|circuit.?breaker)',
            r'(?i)(?:increas|set).*?upstream.*?timeout',
        ],
        'file_path': 'k8s/api-gateway/deployment.yaml',
        'change_type': ChangeType.K8S_MANIFEST,
        'transform': 'update_k8s_env',
    },
    # ── Graceful degradation / retry-after (TokenHandler.java) ──
    {
        'patterns': [
            r'(?i)(?:graceful|degrad|fallback|retry.?after)',
            r'(?i)(?:401|retry_after)',
        ],
        'file_path': 'src/auth-service/TokenHandler.java',
        'change_type': ChangeType.CODE_EDIT,
        'transform': 'update_java_code',
    },
    # ── JWT token fix (TokenHandler.java) ──
    {
        'patterns': [
            r'(?i)jwt.*?(?:token|refresh|expir)',
            r'(?i)token.*?refresh.*?endpoint',
            r'(?i)(?:add|implement).*?auto.?refresh',
        ],
        'file_path': 'src/auth-service/TokenHandler.java',
        'change_type': ChangeType.CODE_EDIT,
        'transform': 'update_java_code',
    },
    # ── Python code fixes (data_validator.py) ──
    {
        'patterns': [
            r'(?i)python.*?(?:error|fix|bug|handl|log|validat)',
            r'(?i)(?:add|fix|implement).*?(?:\btry\b|except\b|error.?handling)',
            r'(?i)(?:fix|patch|update).*?(?:validat|sanitiz|escap).*?(?:input|data)',
            r'(?i)data.*?valid(or|at).*?(?:function|method|class)',
        ],
        'file_path': 'src/data-service/data_validator.py',
        'change_type': ChangeType.CODE_EDIT,
        'transform': 'update_python_code',
    },
    # Python logging / exception handling
    {
        'patterns': [
            r'(?i)log.*?(?:error|exception|fail).*?(?:handl|catch)',
            r'(?i)(?:add|fix).*?except\b.*?(?:block|handler|claus)',
            r'(?i)unhandl.*?(?:except|error|crash)',
        ],
        'file_path': 'src/data-service/data_validator.py',
        'change_type': ChangeType.CODE_EDIT,
        'transform': 'update_python_code',
    },
    # Python input sanitization
    {
        'patterns': [
            r'(?i)sanitiz.*?(?:input|data|user|string)',
            r'(?i)(?:add|implement).*?input.*?(?:clean|sanitiz|validat)',
            r'(?i)inject.*?(?:prevent|protect|guard)',
        ],
        'file_path': 'src/data-service/data_validator.py',
        'change_type': ChangeType.CODE_EDIT,
        'transform': 'update_python_code',
    },
    # ── Database migrations ──
    {
        'patterns': [
            r'(?i)(?:database|db|sql).*?(?:migrat|schema|alter|index|table)',
            r'(?i)(?:add|create|run|write).*?(?:migrat|index|script)',
            r'(?i)ALTER\s+TABLE|CREATE\s+INDEX|migration|schema.?change',
        ],
        'file_path': 'configs/db/migrations/V005__add_payment_indexes.sql',
        'change_type': ChangeType.FILE_CREATE,
        'transform': 'create_sql_migration',
    },
    # Postgres vacuum / reindex / optimize
    {
        'patterns': [
            r'(?i)(?:vacuum|reindex|optimize|VACUUM|REINDEX)',
            r'(?i)(?:table|db|database).*?(?:bloat|wast|frag)',
            r'(?i)WAL.*?(?:archiv|cleanup|retent)',
        ],
        'file_path': 'configs/db/migrations/V005__add_payment_indexes.sql',
        'change_type': ChangeType.FILE_CREATE,
        'transform': 'create_sql_migration',
    },
    # ── Network policy changes ──
    {
        'patterns': [
            r'(?i)(?:network.?policy|firewall|waf).*?(?:rule|config|block|allow)',
            r'(?i)(?:block|restrict|limit).*?(?:IP|access|traffic|CIDR|address)',
            r'(?i)(?:ingress|egress).*?(?:rule|policy|restrict|allow)',
        ],
        'file_path': 'k8s/network-policies/restrict-payment-access.yaml',
        'change_type': ChangeType.K8S_MANIFEST,
        'transform': 'update_k8s_resource',
    },
    # WAF / rate limiting rules
    {
        'patterns': [
            r'(?i)(?:WAF|web.?application.?firewall).*?(?:rule|config|updat)',
            r'(?i)(?:add|block|create).*?WAF.*?rule',
            r'(?i)offend.*?IP.*?(?:block|blacklist|deny)',
        ],
        'file_path': 'k8s/network-policies/restrict-payment-access.yaml',
        'change_type': ChangeType.K8S_MANIFEST,
        'transform': 'update_k8s_resource',
    },
    # ── Redis pool size (configmap) ──
    {
        'patterns': [
            r'(?i)(?:connection|redis)\s*pool\s*(?:size|limit)',
            r'(?i)(?:increas|set|rais).*?(?:pool_size|CONNECTION_POOL_SIZE|pool.size)',
            r'(?i)pool_size\s*(?:from\s*)?\d+\s*(?:to|=>|=)\s*\d+',
        ],
        'file_path': 'configs/payment-processor/configmap.yaml',
        'change_type': ChangeType.CONFIG_EDIT,
        'transform': 'update_yaml_value',
    },
    # ── Pool timeout / backoff (configmap) ──
    {
        'patterns': [
            r'(?i)(?:add|set|increas).*?(?:timeout|retry|backoff)',
            r'(?i)exponential\s*backoff',
            r'(?i)retry\s*with\s*backoff',
        ],
        'file_path': 'configs/payment-processor/configmap.yaml',
        'change_type': ChangeType.CONFIG_EDIT,
        'transform': 'update_yaml_value',
    },
    # ── Redis maxmemory (redis-config.conf) ──
    {
        'patterns': [
            r'(?i)maxmemory\s*(?:limit)?\s*(?:increas|set|rais)',
            r'(?i)(?:increas|set).*?maxmemory',
            r'(?i)maxmemory.*?\d+\s*(?:mb|gb)',
        ],
        'file_path': 'configs/redis/redis-config.conf',
        'change_type': ChangeType.CONFIG_EDIT,
        'transform': 'update_redis_config',
    },
    # ── Cache / TTL (redis-config.conf) ──
    {
        'patterns': [
            r'(?i)(?:ttl|expir|cache).*?(?:key|policy|enforc)',
            r'(?i)(?:add|set).*?expiration.*?policy',
        ],
        'file_path': 'configs/redis/redis-config.conf',
        'change_type': ChangeType.CONFIG_EDIT,
        'transform': 'update_redis_config',
    },
    # ── Postgres connection limit (pgbouncer) ──
    {
        'patterns': [
            r'(?i)(?:postgres|pg|database)\s*(?:max|connection|pool)',
            r'(?i)pg_bouncer.*?max_connections',
            r'(?i)(?:reduc|fix|patch).*?connection\s*(?:pool|leak)',
        ],
        'file_path': 'configs/postgres/pgbouncer-config.yaml',
        'change_type': ChangeType.CONFIG_EDIT,
        'transform': 'update_yaml_value',
    },
    # ── Notification worker OOM / memory ──
    {
        'patterns': [
            r'(?i)(?:oom|memory|OOMKill).*?(?:worker|notification)',
            r'(?i)(?:memory\s*(?:limit|leak)).*?(?:template|render)',
            r'(?i)(?:increas|set).*?(?:memory|resource).*?(?:limit|request)',
            r'(?i)fix.*?file\s*(?:handle|descriptor).*?(?:leak|close)',
        ],
        'file_path': 'k8s/notification-worker/deployment.yaml',
        'change_type': ChangeType.K8S_MANIFEST,
        'transform': 'update_k8s_resource',
    },
    # ── DNS resolution (script) ──
    {
        'patterns': [
            r'(?i)dns.*?resol(?:ution|ve|ver)',
            r'(?i)coredns.*?(?:replica|anti.?affinity|cache)',
            r'(?i)(?:increas|set).*?CoreDNS.*?replica',
        ],
        'change_type': ChangeType.SCRIPT_RUN,
        'command': 'kubectl scale deployment/coredns -n kube-system --replicas=3',
    },
    # ── Kafka consumer lag ──
    {
        'patterns': [
            r'(?i)(?:kafka|consumer)\s*(?:lag|laggard)',
            r'(?i)(?:scal|increas).*?(?:worker|consumer|replica)',
            r'(?i)(?:consumer|replica).*?(?:count|number|scale)',
        ],
        'file_path': 'k8s/notification-worker/deployment.yaml',
        'change_type': ChangeType.K8S_MANIFEST,
        'transform': 'update_k8s_replicas',
    },
    # ── SSL certificate (script) ──
    {
        'patterns': [
            r'(?i)ssl.*?cert(?:ificate)?',
            r'(?i)certbot|renew.*?cert',
            r'(?i)certificate\s*(?:expir|renew|monitor)',
        ],
        'change_type': ChangeType.SCRIPT_RUN,
        'command': 'certbot renew --cert-name api.paystream.io --deploy-hook "nginx -s reload"',
    },
    # ── Generic ConfigMap (catch-all for configmap mentions) ──
    {
        'patterns': [
            r'(?i)(?:configmap|ConfigMap|config.?map)',
            r'(?i)(?:update|edit|modify|patch)\s+ConfigMap',
        ],
        'file_path': 'configs/payment-processor/configmap.yaml',
        'change_type': ChangeType.CONFIG_EDIT,
        'transform': 'update_yaml_value',
    },
    # ── Generic circuit breaker (fallback — api-gateway) ──
    {
        'patterns': [
            r'(?i)circuit.?breaker',
        ],
        'file_path': 'k8s/api-gateway/deployment.yaml',
        'change_type': ChangeType.K8S_MANIFEST,
        'transform': 'update_k8s_env',
    },
]


class TaskGenerator:
    """Generates structured implementation tasks from diagnosis fix steps.

    Uses rule-based pattern matching first, then falls back to LLM-based
    generation for unknown patterns.
    """

    def __init__(self, target_repo_path: str = "fixes/paystream",
                 llm_client: Optional[BaseLLMClient] = None):
        self.target_repo = Path(target_repo_path)
        self._llm_client = llm_client

    def _get_or_create_llm_client(self) -> Optional[BaseLLMClient]:
        """Lazily create an LLM client for fallback task generation."""
        if self._llm_client:
            return self._llm_client
        try:
            router = ModelRouter()
            client, _, _ = router.route(0.0)  # Use powerful model for task gen
            self._llm_client = client
            return client
        except Exception as e:
            logger.warning(f"Could not create LLM client for task generation: {e}")
            return None

    def generate(self, diagnosis_result: Dict[str, Any],
                 incident_log: str = "") -> List[FixTask]:
        """Generate structured fix tasks from a diagnosis result.

        Args:
            diagnosis_result: The full result dict from InferenceEngine.diagnose()
            incident_log: The original raw log (for extra context)

        Returns:
            List of FixTask objects ordered by priority
        """
        diagnosis = diagnosis_result.get('diagnosis', {})
        fix_steps = diagnosis.get('fix_steps', [])
        incident_type = diagnosis_result.get('incident_type', 'NOVEL')
        incident_id = diagnosis_result.get('incident_id', 'unknown')

        if not fix_steps:
            logger.warning(f"[{incident_id}] No fix steps to generate tasks from.")
            return [], ""

        # Determine branch name from root cause
        root_cause = diagnosis.get('root_cause', 'fix')
        safe_name = re.sub(r'[^a-zA-Z0-9]+', '-', root_cause).lower().strip('-')[:40]
        branch_name = f"fix/{incident_id}-{safe_name}"

        # Phase 1: Rule-based pattern matching
        tasks = self._match_patterns(fix_steps, incident_id)

        # Phase 2: For unmatched steps or ambiguous cases, use LLM
        matched_tasks = len(tasks)
        if matched_tasks < len(fix_steps):
            logger.info(
                f"[{incident_id}] {matched_tasks}/{len(fix_steps)} steps matched via rules. "
                f"Using LLM for remainder..."
            )
            llm_tasks = self._generate_with_llm(
                fix_steps, diagnosis_result, incident_log, incident_id, branch_name
            )
            tasks.extend(llm_tasks)

        # Fallback: if still no tasks (no LLM available), create generic ones
        if not tasks:
            tasks = self._create_generic_tasks(fix_steps, incident_id)

        # Assign priorities
        for i, task in enumerate(tasks):
            task.priority = i + 1

        logger.info(
            f"[{incident_id}] Generated {len(tasks)} fix tasks "
            f"({matched_tasks} rule-based, {len(tasks) - matched_tasks} LLM/fallback)"
        )
        return tasks, branch_name

    def _match_patterns(self, fix_steps: List[str],
                        incident_id: str) -> List[FixTask]:
        """Match fix steps against known patterns using rules."""
        tasks: List[FixTask] = []
        seen_paths: set = set()

        for step_idx, step in enumerate(fix_steps):
            for pattern_def in FIX_PATTERNS:
                for pat in pattern_def['patterns']:
                    if re.search(pat, step):
                        file_path = pattern_def.get('file_path', '')
                        if file_path and file_path in seen_paths:
                            continue

                        task = FixTask(
                            id=f"{incident_id}-task-{step_idx + 1:02d}",
                            description=step,
                            change_type=pattern_def['change_type'],
                            file_path=file_path if file_path else '',
                            command=pattern_def.get('command'),
                            priority=step_idx + 1,
                        )
                        tasks.append(task)
                        if file_path:
                            seen_paths.add(file_path)
                        break
                else:
                    continue
                break

        return tasks

    def _generate_with_llm(self, fix_steps: List[str],
                           diagnosis_result: Dict[str, Any],
                           incident_log: str,
                           incident_id: str,
                           branch_name: str) -> List[FixTask]:
        """Use LLM to analyze fix steps and generate structured tasks."""
        client = self._get_or_create_llm_client()
        if not client:
            return []

        # Find unmatched steps
        diagnosis = diagnosis_result.get('diagnosis', {})
        extracted = diagnosis_result.get('extracted_fields', {})
        service = extracted.get('service', 'unknown')
        error_type = extracted.get('error_type', 'unknown')

        # Build repo structure description
        repo_structure = self._describe_repo_structure()

        prompt = (
            f"You are an SRE automation engineer. Given these fix steps from an "
            f"incident diagnosis, generate structured implementation tasks.\n\n"
            f"Incident: {incident_id}\n"
            f"Service: {service}\n"
            f"Error Type: {error_type}\n"
            f"Root Cause: {diagnosis.get('root_cause', '')}\n\n"
            f"Fix Steps:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(fix_steps)) + "\n\n"
            f"Target Repository Structure:\n{repo_structure}\n\n"
            f"Output a JSON list of tasks. Each task must have:\n"
            f"- description: The fix step text\n"
            f"- file_path: Path relative to repo root that needs changing (empty string if no file)\n"
            f"- change_type: One of: config_edit, code_edit, file_create, k8s_manifest, script_run\n"
            f"- command: Shell command to run (only for script_run; empty string otherwise)\n\n"
            f"Output ONLY valid JSON, no markdown, no explanation."
        )

        try:
            from src.prompts.templates import SYSTEM_PROMPT
            response = client.generate(
                "You are a precise remediation planner. Output only valid JSON.",
                prompt,
                max_tokens=2048,
                temperature=0.2,
            )

            import json as json_lib

            # Strip markdown fences if the LLM wrapped JSON in ```json ... ```
            raw_content = response.content.strip()
            if '```' in raw_content:
                # Extract content between markdown fences
                import re as _re
                fence_match = _re.search(r'```(?:json)?\s*\n?(.*?)\n?```',
                                          raw_content, _re.DOTALL)
                if fence_match:
                    raw_content = fence_match.group(1).strip()
                else:
                    # Remove any remaining fences
                    raw_content = _re.sub(r'```(?:json)?', '', raw_content).strip()

            tasks_data = json_lib.loads(raw_content)
            if isinstance(tasks_data, dict):
                tasks_data = [tasks_data]

            tasks = []
            for i, td in enumerate(tasks_data):
                change_type_str = td.get('change_type', 'config_edit')
                try:
                    change_type = ChangeType(change_type_str)
                except ValueError:
                    change_type = ChangeType.CONFIG_EDIT

                tasks.append(FixTask(
                    id=f"{incident_id}-task-{i + 1:02d}",
                    description=td.get('description', fix_steps[i] if i < len(fix_steps) else ''),
                    change_type=change_type,
                    file_path=td.get('file_path', ''),
                    command=td.get('command', '') or None,
                    priority=i + 1,
                ))
            return tasks

        except Exception as e:
            logger.warning(f"LLM task generation failed: {e}")
            return []

    def _describe_repo_structure(self) -> str:
        """Describe the target repo file structure for LLM prompts."""
        if not self.target_repo.exists():
            return "(Simulated repository not yet created)"

        lines = []
        for path in sorted(self.target_repo.rglob('*')):
            if path.is_file() and '__pycache__' not in str(path):
                rel = path.relative_to(self.target_repo)
                lines.append(f"  {rel}")
        return "\n".join(lines)

    def _create_generic_tasks(self, fix_steps: List[str],
                              incident_id: str) -> List[FixTask]:
        """Create generic fallback tasks when no other method works."""
        tasks = []
        for i, step in enumerate(fix_steps):
            # Try to infer a reasonable file path
            file_path = self._infer_file_path(step)

            tasks.append(FixTask(
                id=f"{incident_id}-task-{i + 1:02d}",
                description=step,
                change_type=ChangeType.CONFIG_EDIT,
                file_path=file_path,
                priority=i + 1,
            ))
        return tasks

    def _infer_file_path(self, step: str) -> str:
        """Try to infer a relevant file path from a fix step description."""
        step_lower = step.lower()

        mapping = [
            # Most specific patterns first
            (r'(?i)postgres|pg_bouncer|database', 'configs/postgres/pgbouncer-config.yaml'),
            (r'(?i)redis.*config|cache.*config|maxmemory', 'configs/redis/redis-config.conf'),
            (r'(?i)gateway|upstream|timeout|proxy', 'k8s/api-gateway/deployment.yaml'),
            (r'(?i)oom|memory|worker|notification', 'k8s/notification-worker/deployment.yaml'),
            (r'(?i)kafka|consumer|lag', 'k8s/notification-worker/deployment.yaml'),
            (r'(?i)jwt|auth|token', 'src/auth-service/TokenHandler.java'),
            (r'(?i)cert|ssl|tls', 'ci/.github/workflows/cert-renewal.yml'),
            (r'(?i)dns|coredns', 'k8s/coredns/deployment.yaml'),
            (r'(?i)ml|model|inference|batch', 'k8s/fraud-detection-ml/deployment.yaml'),
            (r'(?i)redis|pool|connection', 'configs/payment-processor/configmap.yaml'),
        ]

        for pattern, path in mapping:
            if re.search(pattern, step_lower):
                return path

        return ''
