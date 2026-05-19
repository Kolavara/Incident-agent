"""GitHub integration module — creates branches, commits, and pull requests.

Uses the GitHub REST API (via `requests`) to:
1. Create a new branch from main
2. Commit file changes via the Contents API
3. Create a pull request with a structured body
4. Push everything to GitHub

Handles authentication via GITHUB_TOKEN environment variable.
Gracefully degrades to local-only mode when no token is available.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from src.remediation.models import (
    ChangeType, FixStatus, FixTask, PRResult, RemediationPlan,
)

logger = logging.getLogger('incident_agent.remediation.github_pusher')


GITHUB_API_BASE = "https://api.github.com"


class GitHubPusher:
    """Creates GitHub pull requests from applied fixes.

    Flow:
    1. Initialize git repo if not already set up
    2. Stage and commit changed files
    3. Create a new branch with the fix changes
    4. Push to GitHub (via API or git remote)
    5. Create a pull request with structured description

    Falls back to local-only (git with no remote) if GitHub API
    is not configured.
    """

    def __init__(self, target_repo_path: str = "fixes/paystream"):
        self.target_repo = Path(target_repo_path).resolve()
        self.token = os.getenv('GITHUB_TOKEN', '')
        self.repo_owner = os.getenv('GITHUB_REPO_OWNER', '')
        self.repo_name = os.getenv('GITHUB_REPO_NAME', 'paystream-infra')

        # Derive repo info from git remote if available
        self._remote_info = self._detect_remote_info()

        # Detect gh CLI availability
        self._gh_path = self._detect_gh_cli()

    def _detect_remote_info(self) -> Optional[Dict[str, str]]:
        """Try to detect GitHub remote URL from git config."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.target_repo), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Parse git@github.com:owner/repo.git or https://...
                if "github.com" in url:
                    parts = url.replace("git@github.com:", "").replace(
                        "https://github.com/", ""
                    ).rstrip(".git").split("/")
                    if len(parts) >= 2:
                        return {
                            'owner': parts[0],
                            'repo': parts[1],
                        }
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None

    def create_pull_request(self, plan: RemediationPlan) -> PRResult:
        """Create a pull request with the fix changes.

        Steps:
        1. Initialize local git repo if needed
        2. Stage and commit changes
        3. Create PR body from plan
        4. Push via gh CLI, API, or git remote
        5. Return PR URL

        Priority:
        1. gh CLI (if installed and authenticated)
        2. GitHub REST API (if token has permissions)
        3. git push (fallback — branch + PR URL only)

        Args:
            plan: The remediation plan with applied tasks

        Returns:
            PRResult with PR URL and branch info
        """
        pr_result = PRResult()

        # Step 1: Initialize git repo
        if not self._init_git():
            pr_result.error = "Failed to initialize git repository"
            logger.error(pr_result.error)
            return pr_result

        # Step 2: Stage and commit changes
        commit_result = self._commit_changes(plan)
        if commit_result == 'failed':
            pr_result.error = "Failed to commit changes"
            logger.error(pr_result.error)
            return pr_result
        if commit_result == 'no_changes':
            logger.info("No file changes to commit — no pull request needed.")
            pr_result.success = True
            pr_result.error = ""
            pr_result.branch_url = "local://no-changes"
            pr_result.pr_url = ""
            # Clean up temp PR body if it exists
            pr_body_path = self.target_repo / ".pr_body.md"
            if pr_body_path.exists():
                pr_body_path.unlink()
            return pr_result

        # Step 3: Build PR description
        pr_body = self._build_pr_body(plan)
        pr_body_path = self.target_repo / ".pr_body.md"
        pr_body_path.write_text(pr_body, encoding='utf-8')

        # Step 4: Push and create PR (gh CLI → API → git push)
        if self._gh_path:
            owner = self.repo_owner or (self._remote_info['owner'] if self._remote_info else 'Kolavara')
            repo = self.repo_name or (self._remote_info['repo'] if self._remote_info else 'paystream-infra')
            pr_result = self._push_via_gh_cli(plan, owner, repo, pr_body)

        if not pr_result.success and self.token and (self.repo_owner or (self._remote_info and self._remote_info.get('owner'))):
            owner = self.repo_owner or (self._remote_info['owner'] if self._remote_info else '')
            repo = self.repo_name or (self._remote_info['repo'] if self._remote_info else '')
            pr_result = self._push_via_api(
                plan, owner, repo, pr_body
            )

        if not pr_result.success:
            logger.info("Previous methods unavailable or failed — falling back to git push")
            git_result = self._push_via_git(plan)
            if git_result.success:
                pr_result.success = True
                pr_result.branch_url = git_result.branch_url
                pr_result.error = ""
                # If git push was truly local-only (no remote), keep the local URL
                if git_result.branch_url and git_result.branch_url.startswith('local://'):
                    pr_result.pr_url = f"file://{self.target_repo}/ (local branch: {plan.branch_name})"
                    logger.info(f"Changes committed locally to branch '{plan.branch_name}'")
                else:
                    owner_str = self.repo_owner or (self._remote_info['owner'] if self._remote_info else 'Kolavara')
                    repo_str = self.repo_name or (self._remote_info['repo'] if self._remote_info else 'paystream-infra')
                    pr_result.pr_url = f"https://github.com/{owner_str}/{repo_str}/pull/new/{plan.branch_name}"
                    pr_result.branch_url = plan.branch_name
                    logger.info(f"Branch pushed via git: {pr_result.pr_url}")

        # Clean up temp PR body
        if pr_body_path.exists():
            pr_body_path.unlink()

        return pr_result

    def _init_git(self) -> bool:
        """Ensure the target repo is a git repository."""
        git_dir = self.target_repo / ".git"
        if git_dir.exists():
            return True

        try:
            subprocess.run(
                ["git", "-C", str(self.target_repo), "init"],
                capture_output=True, text=True, timeout=10, check=True,
            )
            # Create initial commit on main branch
            readme = self.target_repo / "README.md"
            if readme.exists():
                subprocess.run(
                    ["git", "-C", str(self.target_repo), "add", "."],
                    capture_output=True, text=True, timeout=10, check=True,
                )
                subprocess.run(
                    ["git", "-C", str(self.target_repo), "commit", "-m", "Initial commit"],
                    capture_output=True, text=True, timeout=10, check=True,
                )
            logger.info(f"Initialized git repo at {self.target_repo}")
            return True
        except subprocess.SubprocessError as e:
            logger.warning(f"Failed to init git: {e}")
            return False

    def _commit_changes(self, plan: RemediationPlan) -> str:
        """Stage and commit file changes in the target repo.

        Returns:
            'ok' — changes were committed to a new branch
            'no_changes' — no files were modified (script-only fix)
            'failed' — git error occurred
        """
        try:
            # Add all changed files
            subprocess.run(
                ["git", "-C", str(self.target_repo), "add", "-A"],
                capture_output=True, text=True, timeout=10, check=True,
            )

            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "-C", str(self.target_repo), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
            )
            if not status.stdout.strip():
                logger.info("No changes to commit (script-only fix or already up to date).")
                return 'no_changes'

            # Create branch
            subprocess.run(
                ["git", "-C", str(self.target_repo), "checkout", "-b", plan.branch_name],
                capture_output=True, text=True, timeout=10, check=True,
            )

            # Build commit message
            commit_msg = f"fix({plan.incident_id}): {plan.pr_title}\n\n{plan.summary}"
            subprocess.run(
                ["git", "-C", str(self.target_repo), "commit", "-m", commit_msg],
                capture_output=True, text=True, timeout=10, check=True,
            )

            logger.info(f"Committed changes to branch '{plan.branch_name}'")
            return 'ok'

        except subprocess.SubprocessError as e:
            logger.error(f"Git commit failed: {e}")
            return 'failed'

    def _push_via_api(self, plan: RemediationPlan, owner: str,
                      repo: str, pr_body: str) -> PRResult:
        """Push changes and create PR using GitHub REST API."""
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        result = PRResult()

        try:
            # Step 1: Get the main branch's latest SHA
            repo_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
            refs_url = f"{repo_url}/git/ref/heads/main"

            resp = requests.get(refs_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                result.error = f"Cannot get main branch ref: {resp.status_code} {resp.text[:200]}"
                logger.warning(result.error)
                return result

            main_sha = resp.json()['object']['sha']

            # Step 2: Create a new branch from main
            branch_ref = f"refs/heads/{plan.branch_name}"
            resp = requests.post(
                f"{repo_url}/git/refs",
                headers=headers,
                json={"ref": branch_ref, "sha": main_sha},
                timeout=15,
            )
            if resp.status_code not in (201, 422):  # 422 = branch exists
                result.error = f"Cannot create branch: {resp.status_code} {resp.text[:200]}"
                logger.warning(result.error)
                branch_created = False
            else:
                branch_created = True
                result.branch_url = f"https://github.com/{owner}/{repo}/tree/{plan.branch_name}"

            # Step 3: Commit each changed file via the Contents API
            if branch_created:
                for task in plan.tasks:
                    if task.status == FixStatus.APPLIED and task.file_path:
                        self._api_commit_file(
                            repo_url, headers, plan.branch_name,
                            task.file_path, task.new_content or "",
                            f"fix: {task.description[:80]}"
                        )

            # Step 4: Create pull request
            resp = requests.post(
                f"{repo_url}/pulls",
                headers=headers,
                json={
                    "title": plan.pr_title,
                    "head": plan.branch_name,
                    "base": "main",
                    "body": pr_body,
                },
                timeout=15,
            )

            if resp.status_code == 201:
                pr_data = resp.json()
                result.success = True
                result.pr_url = pr_data.get('html_url', '')
                result.pr_number = pr_data.get('number')
                logger.info(
                    f"PR created: #{result.pr_number} at {result.pr_url}"
                )
            elif resp.status_code == 422:
                # PR already exists
                result.success = True
                result.pr_url = f"https://github.com/{owner}/{repo}/pull/new/{plan.branch_name}"
                result.pr_number = None
                logger.info("PR may already exist (422). Branch is available.")
            else:
                result.error = f"PR creation failed: {resp.status_code} {resp.text[:200]}"

        except requests.RequestException as e:
            result.error = f"GitHub API request failed: {e}"
            logger.error(result.error)

        return result

    def _api_commit_file(self, repo_url: str, headers: Dict, branch: str,
                         file_path: str, content: str, message: str):
        """Commit a single file via GitHub Contents API."""
        try:
            # Check if file exists
            resp = requests.get(
                f"{repo_url}/contents/{file_path}",
                headers=headers,
                params={"ref": branch},
                timeout=15,
            )
            sha = resp.json().get('sha') if resp.status_code == 200 else None

            # Create or update file
            payload = {
                "message": message,
                "content": self._to_base64(content),
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha

            resp = requests.put(
                f"{repo_url}/contents/{file_path}",
                headers=headers,
                json=payload,
                timeout=15,
            )
            if resp.status_code in (200, 201):
                logger.info(f"  API committed: {file_path}")
            else:
                logger.warning(f"  API commit failed for {file_path}: {resp.status_code}")

        except requests.RequestException as e:
            logger.warning(f"  API commit error for {file_path}: {e}")

    def _detect_gh_cli(self) -> Optional[str]:
        """Check if GitHub CLI (gh) is installed and authenticated.

        Returns:
            Path to gh executable if available, None otherwise
        """
        # Common gh locations on Windows and Unix
        candidates = [
            "gh",
            "gh.exe",
            "C:\\Program Files\\GitHub CLI\\gh.exe",
            "C:\\Program Files (x86)\\GitHub CLI\\gh.exe",
        ]
        for cmd in candidates:
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    # Also verify it's authenticated
                    auth_result = subprocess.run(
                        [cmd, "auth", "status"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if auth_result.returncode == 0:
                        logger.info(f"GitHub CLI detected: {cmd}")
                        return cmd
                    else:
                        logger.warning(
                            f"GitHub CLI found at {cmd} but not authenticated. "
                            f"Run 'gh auth login' first."
                        )
                        return None
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                continue
        logger.info("GitHub CLI (gh) not found — will use API or git fallback")
        return None

    def _push_via_gh_cli(self, plan: RemediationPlan, owner: str,
                         repo: str, pr_body: str) -> PRResult:
        """Push changes and create PR using GitHub CLI (gh).

        Uses gh CLI which authenticates via its own credential store
        (keyring). Falls through if the token lacks GraphQL permissions.

        Args:
            plan: Remediation plan with branch info
            owner: GitHub repo owner
            repo: GitHub repo name
            pr_body: PR description body (already written to .pr_body.md
                    by create_pull_request before calling this method)

        Returns:
            PRResult with PR URL and status
        """
        result = PRResult()
        gh = self._gh_path or "gh"

        try:
            # Step 1: Push the branch first via git
            push = subprocess.run(
                ["git", "-C", str(self.target_repo), "push", "-u", "origin", plan.branch_name],
                capture_output=True, text=True, timeout=30,
            )
            if push.returncode != 0:
                logger.warning(f"Git push failed before gh PR create: {push.stderr[:200]}")

            # Step 2: Create PR via gh CLI
            repo_ref = f"{owner}/{repo}"
            pr_cmd = subprocess.run(
                [
                    gh, "pr", "create",
                    "--repo", repo_ref,
                    "--base", "main",
                    "--head", plan.branch_name,
                    "--title", plan.pr_title,
                    "--body", pr_body,
                ],
                capture_output=True, text=True, timeout=30,
            )

            if pr_cmd.returncode == 0:
                pr_url = pr_cmd.stdout.strip()
                result.success = True
                result.branch_url = plan.branch_name
                result.pr_url = pr_url
                # Extract PR number from URL: https://github.com/owner/repo/pull/123
                if pr_url and '/pull/' in pr_url:
                    try:
                        result.pr_number = int(pr_url.rsplit('/pull/', 1)[-1])
                    except (ValueError, IndexError):
                        pass
                logger.info(
                    f"PR created via gh CLI: #{result.pr_number} at {result.pr_url}"
                )
            else:
                error_msg = pr_cmd.stderr.strip()[:300] or pr_cmd.stdout.strip()[:300]
                # Check if PR already exists (not a failure)
                if 'already exists' in error_msg.lower() or 'already' in error_msg.lower():
                    result.success = True
                    result.branch_url = plan.branch_name
                    result.pr_url = f"https://github.com/{owner}/{repo}/pull/new/{plan.branch_name}"
                    logger.info(f"PR already exists for branch '{plan.branch_name}'")
                else:
                    result.error = f"gh CLI failed: {error_msg}"
                    logger.warning(result.error)

        except subprocess.SubprocessError as e:
            result.error = f"gh CLI execution failed: {e}"
            logger.warning(result.error)
        except (OSError, IOError) as e:
            result.error = f"gh CLI I/O error: {e}"
            logger.warning(result.error)

        return result

    def _push_via_git(self, plan: RemediationPlan) -> PRResult:
        """Push changes using local git (no GitHub API)."""
        result = PRResult()

        try:
            # Try to push to configured remote
            push = subprocess.run(
                ["git", "-C", str(self.target_repo), "push", "-u", "origin", plan.branch_name],
                capture_output=True, text=True, timeout=30,
            )
            if push.returncode == 0:
                result.success = True
                result.branch_url = plan.branch_name
                logger.info(f"Pushed branch '{plan.branch_name}' to origin")
            else:
                # No remote configured — local-only
                logger.info(
                    f"No git remote configured. Changes committed locally on "
                    f"branch '{plan.branch_name}'."
                )
                result.success = True
                result.branch_url = f"local://{plan.branch_name}"

        except subprocess.SubprocessError as e:
            logger.warning(f"Git push failed (local-only mode): {e}")
            result.success = True  # Still considered success locally
            result.branch_url = f"local://{plan.branch_name}"

        return result

    def _build_pr_body(self, plan: RemediationPlan) -> str:
        """Build a structured pull request description."""
        lines = [
            f"## 🛠️ Automated Remediation: #{plan.incident_id}",
            "",
            plan.summary,
            "",
            "### Incident Details",
            f"- **Incident ID:** {plan.incident_id}",
            f"- **Type:** {plan.incident_type}",
            "",
            "### Changes Applied",
            "",
        ]

        for task in plan.tasks:
            if task.status == FixStatus.APPLIED:
                status_icon = "✅"
            elif task.status == FixStatus.FAILED:
                status_icon = "❌"
            elif task.status == FixStatus.SKIPPED:
                status_icon = "⏭️"
            else:
                status_icon = "⏳"

            lines.append(f"| {status_icon} | {task.description} |")
            if task.file_path:
                lines.append(f"  | File: `{task.file_path}` |")
            if task.change_type.value == "script_run":
                lines.append(f"  | Command: `{task.command or task.description}` |")
            lines.append("")

        lines.extend([
            "",
            "### Validation",
        ])

        if plan.tasks:
            applied = sum(1 for t in plan.tasks if t.status == FixStatus.APPLIED)
            failed = sum(1 for t in plan.tasks if t.status == FixStatus.FAILED)
            lines.append(f"- **Applied:** {applied} fix tasks")
            lines.append(f"- **Failed:** {failed} fix tasks")

        lines.extend([
            "",
            "### Rollback Instructions",
            "```bash",
            f"git revert {plan.branch_name}",
            "```",
            "",
            "---",
            "_🤖 Generated by Incident Response Agent_",
        ])

        return "\n".join(lines)

    @staticmethod
    def _to_base64(content: str) -> str:
        """Encode content to base64 for GitHub API."""
        import base64
        return base64.b64encode(content.encode('utf-8')).decode('utf-8')

    def check_config(self) -> Dict[str, bool]:
        """Check if GitHub integration is properly configured.

        Returns:
            Dict with keys: has_token, has_remote, can_push, has_gh_cli
        """
        token_ok = bool(self.token)
        remote_ok = self._remote_info is not None
        gh_ok = self._gh_path is not None

        git_ok = False
        try:
            git_dir = self.target_repo / ".git"
            git_ok = git_dir.exists()
        except Exception:
            pass

        return {
            'has_token': token_ok,
            'has_remote': remote_ok,
            'has_gh_cli': gh_ok,
            'git_initialized': git_ok,
            'can_push': token_ok or remote_ok or gh_ok,
        }
