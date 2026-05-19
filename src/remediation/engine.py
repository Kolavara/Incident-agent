"""Remediation engine — orchestrates the full pipeline from diagnosis to PR.

Coordinates:
1. Task generation (step 5)
2. Fix implementation (step 6 → actually step 7 in user's flow, but we embed test gen between)
3. Test generation (step 6)
4. Validation (step 8)
5. PR creation (step 9)
6. Push to GitHub (step 10)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from src.remediation.models import (
    ChangeType, FixStatus, FixTask, RemediationPlan,
    ValidationResult, PRResult, RemediationResult,
)
from src.remediation.task_generator import TaskGenerator
from src.remediation.fixer import Fixer
from src.remediation.test_generator import TestGenerator
from src.remediation.validator import Validator
from src.remediation.github_pusher import GitHubPusher

logger = logging.getLogger('incident_agent.remediation.engine')


class RemediationEngine:
    """End-to-end remediation orchestrator.

    Usage:
        engine = RemediationEngine()
        result = engine.run(diagnosis_result)
        print(result.plan.pr_title)
        print(result.pr.pr_url)
    """

    def __init__(self, target_repo_path: str = "fixes/paystream",
                 dry_run: bool = False, simulate_validation: bool = True):
        self.target_repo = Path(target_repo_path)
        self.dry_run = dry_run
        self.task_generator = TaskGenerator(target_repo_path)
        self.fixer = Fixer(target_repo_path, dry_run=dry_run)
        self.test_generator = TestGenerator(target_repo_path)
        self.validator = Validator(target_repo_path, simulate=simulate_validation)
        self.github_pusher = GitHubPusher(target_repo_path)
        self._last_plan: Optional[RemediationPlan] = None

    def plan(self, diagnosis_result: Dict[str, Any],
             incident_log: str = "") -> RemediationPlan:
        """Step 5: Generate a remediation plan without applying it.

        Args:
            diagnosis_result: Result from InferenceEngine.diagnose()
            incident_log: The original raw log for extra context

        Returns:
            RemediationPlan with structured tasks
        """
        diagnosis = diagnosis_result.get('diagnosis', {})
        fix_steps = diagnosis.get('fix_steps', [])
        incident_id = diagnosis_result.get('incident_id', 'unknown')
        incident_type = diagnosis_result.get('incident_type', 'NOVEL')
        root_cause = diagnosis.get('root_cause', 'Unknown cause')

        # Generate tasks
        tasks, branch_name = self.task_generator.generate(
            diagnosis_result, incident_log
        )

        # Build PR title from root cause
        pr_title = f"fix: {root_cause[:80]}"

        # Build summary
        steps_summary = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(fix_steps))

        plan = RemediationPlan(
            incident_id=incident_id,
            incident_type=incident_type,
            tasks=tasks,
            branch_name=branch_name or f"fix/{incident_id}-auto",
            pr_title=pr_title,
            pr_description=f"Automated remediation for incident {incident_id}",
            summary=f"## Root Cause\n{root_cause}\n\n## Fix Steps\n{steps_summary}",
        )

        self._last_plan = plan
        return plan

    def apply(self, plan: RemediationPlan) -> bool:
        """Steps 6-7: Apply fix tasks and generate tests.

        First applies all fix tasks (config edits, code changes, etc.),
        then generates validation test files for the applied fixes.

        Args:
            plan: The remediation plan to execute

        Returns:
            True if all fix tasks were applied successfully
        """
        # Step 7: Apply fix implementations
        applied, failed = self.fixer.apply_all(plan.tasks)
        logger.info(
            f"[{plan.incident_id}] Fixes: {applied} applied, {failed} failed"
        )

        # Step 6: Generate tests for applied fixes
        if applied > 0:
            test_tasks = self.test_generator.generate(plan.tasks)
            plan.tasks.extend(test_tasks)
            logger.info(
                f"[{plan.incident_id}] Generated {len(test_tasks)} test files"
            )
        else:
            logger.warning(f"[{plan.incident_id}] No fixes applied — skipping tests")

        return failed == 0

    def validate(self, plan: RemediationPlan,
                 run_live: bool = False) -> ValidationResult:
        """Step 8: Run validation tests on applied fixes.

        Args:
            plan: The remediation plan with applied tasks
            run_live: If True, actually runs pytest

        Returns:
            ValidationResult with test pass/fail details
        """
        # Count generated test files
        test_tasks = [t for t in plan.tasks if t.id.startswith('test-')]
        applied_tasks = [t for t in plan.tasks if t.status == FixStatus.APPLIED]

        validation = self.validator.validate(
            test_tasks_count=len(test_tasks),
            applied_tasks_count=len(applied_tasks),
            run_live=run_live,
        )

        return validation

    def create_pr(self, plan: RemediationPlan) -> PRResult:
        """Steps 9-10: Create PR-ready code and push to GitHub.

        Commits all changes to a local branch and pushes to GitHub
        (via API or git remote). Creates a structured pull request.

        Args:
            plan: The remediation plan with applied tasks

        Returns:
            PRResult with PR URL, branch info, and status
        """
        pr_result = self.github_pusher.create_pull_request(plan)
        return pr_result

    def run(self, diagnosis_result: Dict[str, Any],
            incident_log: str = "",
            run_live_tests: bool = False) -> RemediationResult:
        """Run the full remediation pipeline (steps 5-10).

        Args:
            diagnosis_result: Result from InferenceEngine.diagnose()
            incident_log: The original raw log for context
            run_live_tests: If True, actually run pytest

        Returns:
            RemediationResult with plan, validation, and PR info
        """
        result = RemediationResult()

        try:
            # Step 5: Generate implementation tasks
            logger.info("Step 5: Generating implementation tasks...")
            plan = self.plan(diagnosis_result, incident_log)
            result.plan = plan

            if not plan.tasks:
                result.error = "No fix tasks could be generated from diagnosis"
                logger.warning(result.error)
                return result

            # Steps 6-7: Apply fixes + generate tests
            logger.info("Steps 6-7: Applying fixes and generating tests...")
            all_applied = self.apply(plan)
            result.applied_tasks = len([t for t in plan.tasks
                                       if t.status == FixStatus.APPLIED])
            result.failed_tasks = len([t for t in plan.tasks
                                      if t.status == FixStatus.FAILED])

            if not all_applied:
                logger.warning("Some fix tasks failed. Continuing with validation...")

            # Step 8: Run validation
            logger.info("Step 8: Running validation tests...")
            validation = self.validate(plan, run_live=run_live_tests)
            result.validation = validation

            # Steps 9-10: Create PR and push
            logger.info("Steps 9-10: Creating PR and pushing to GitHub...")
            pr = self.create_pr(plan)
            result.pr = pr

            if pr.success:
                logger.info(
                    f"Remediation complete! "
                    f"PR: {pr.pr_url}"
                )
            else:
                logger.warning(
                    f"Remediation applied locally. "
                    f"Push to GitHub manually: git push origin {plan.branch_name}"
                )

        except Exception as e:
            logger.exception(f"Remediation pipeline failed: {e}")
            result.error = str(e)

        return result

    def get_last_plan(self) -> Optional[RemediationPlan]:
        """Get the most recently generated remediation plan."""
        return self._last_plan

    def get_diff(self) -> str:
        """Get a diff of all changes from the last remediation run."""
        return self.fixer.get_diff()
