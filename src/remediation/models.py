"""Data models for the remediation pipeline (steps 5–10)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class ChangeType(Enum):
    """Types of changes that can be applied as part of a fix."""
    CONFIG_EDIT = "config_edit"           # Modify a config file (YAML, conf, etc.)
    CODE_EDIT = "code_edit"               # Modify source code
    FILE_CREATE = "file_create"           # Create a new file
    K8S_MANIFEST = "k8s_manifest"         # Modify a Kubernetes manifest
    SCRIPT_RUN = "script_run"             # Run a command (e.g. certbot, kubectl)


class FixStatus(Enum):
    """Status of an individual fix task."""
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FixTask:
    """A single actionable fix task derived from diagnosis fix steps.

    Attributes:
        id: Unique task identifier.
        description: Human-readable description of the fix.
        change_type: Category of change.
        file_path: Path relative to the target repository root.
        original_content: Existing file content before change (if applicable).
        new_content: New file content after applying the fix (if applicable).
        command: Shell command to run (for SCRIPT_RUN tasks).
        status: Current execution status.
        priority: Execution order (lower = first).
    """
    id: str
    description: str
    change_type: ChangeType
    file_path: str
    original_content: Optional[str] = None
    new_content: Optional[str] = None
    command: Optional[str] = None
    status: FixStatus = FixStatus.PENDING
    priority: int = 1


@dataclass
class RemediationPlan:
    """A structured plan generated from diagnosis fix steps.

    Attributes:
        incident_id: The incident being remediated.
        incident_type: KNOWN / PARTIAL / NOVEL.
        tasks: Ordered list of fix tasks to apply.
        branch_name: Git branch to create for the fix.
        pr_title: Title for the GitHub pull request.
        pr_description: Body text for the pull request.
        summary: Short summary of what the plan achieves.
    """
    incident_id: str
    incident_type: str = "NOVEL"
    tasks: List[FixTask] = field(default_factory=list)
    branch_name: str = ""
    pr_title: str = ""
    pr_description: str = ""
    summary: str = ""


@dataclass
class ValidationResult:
    """Result of running validation tests on applied fixes."""
    passed: bool = False
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    errors: List[str] = field(default_factory=list)
    output: str = ""


@dataclass
class PRResult:
    """Result of the GitHub PR/push operation."""
    success: bool = False
    branch_url: str = ""
    pr_url: str = ""
    pr_number: Optional[int] = None
    error: Optional[str] = None


@dataclass
class RemediationResult:
    """Aggregated result of the full remediation pipeline (steps 5–10)."""
    plan: Optional[RemediationPlan] = None
    applied_tasks: int = 0
    failed_tasks: int = 0
    validation: Optional[ValidationResult] = None
    pr: Optional[PRResult] = None
    error: Optional[str] = None
