"""Unit tests for the GitHub pusher module."""

import sys
import os
import json
import subprocess
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.remediation.github_pusher import GitHubPusher
from src.remediation.models import (
    ChangeType, FixStatus, FixTask, RemediationPlan, PRResult,
)


class TestGitHubPusherInit(unittest.TestCase):
    """Test GitHubPusher initialization."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.remediation.github_pusher.GitHubPusher._detect_remote_info')
    def test_init_default_path(self, mock_detect):
        mock_detect.return_value = None
        os.environ.pop('GITHUB_TOKEN', None)
        os.environ.pop('GITHUB_REPO_OWNER', None)
        os.environ.pop('GITHUB_REPO_NAME', None)
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        self.assertEqual(str(pusher.target_repo), os.path.realpath(self.temp_dir))
        self.assertEqual(pusher.token, "")
        self.assertEqual(pusher.repo_name, "paystream-infra")

    @patch('src.remediation.github_pusher.GitHubPusher._detect_remote_info')
    def test_init_with_token(self, mock_detect):
        mock_detect.return_value = None
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'ghp_test123'}):
            pusher = GitHubPusher(target_repo_path=self.temp_dir)
            self.assertEqual(pusher.token, 'ghp_test123')

    @patch('src.remediation.github_pusher.GitHubPusher._detect_remote_info')
    def test_init_detects_remote(self, mock_detect):
        mock_detect.return_value = {'owner': 'my-org', 'repo': 'my-repo'}
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        self.assertEqual(pusher._remote_info, {'owner': 'my-org', 'repo': 'my-repo'})


class TestGitHubPusherDetectRemote(unittest.TestCase):
    """Test remote info detection."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('subprocess.run')
    def test_detects_ssh_remote(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:my-org/my-infra.git\n"
        mock_run.return_value = mock_result

        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        info = pusher._remote_info
        self.assertEqual(info, {'owner': 'my-org', 'repo': 'my-infra'})

    @patch('subprocess.run')
    def test_detects_https_remote(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/acme/paystream.git\n"
        mock_run.return_value = mock_result

        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        info = pusher._remote_info
        self.assertEqual(info, {'owner': 'acme', 'repo': 'paystream'})

    @patch('subprocess.run')
    def test_handles_no_remote(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        self.assertIsNone(pusher._remote_info)


class TestGitHubPusherInitGit(unittest.TestCase):
    """Test git initialization."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_git_already_exists(self):
        (Path(self.temp_dir) / ".git").mkdir()
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        self.assertTrue(pusher._init_git())

    @patch('subprocess.run')
    def test_init_git_successful(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        result = pusher._init_git()
        # Should succeed since the fixture dir exists
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_init_git_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, 'git')
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        self.assertFalse(pusher._init_git())


class TestGitHubPusherCommit(unittest.TestCase):
    """Test git commit flow."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Create a minimal git repo
        git_dir = Path(self.temp_dir) / ".git"
        git_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_plan(self, branch="fix/INC-014-test") -> RemediationPlan:
        return RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name=branch,
            pr_title="fix: test",
            summary="Test summary",
        )

    @patch('subprocess.run')
    def test_commit_changes_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = self._make_plan()
        result = pusher._commit_changes(plan)
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_commit_changes_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, 'git')
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = self._make_plan()
        result = pusher._commit_changes(plan)
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_commit_no_changes(self, mock_run):
        def mock_side_effect(*args, **kwargs):
            cmd = args[0]
            result = MagicMock(returncode=0)
            if "status" in str(cmd):
                result.stdout = ""
            return result

        mock_run.side_effect = mock_side_effect
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = self._make_plan()
        result = pusher._commit_changes(plan)
        self.assertTrue(result)


class TestGitHubPusherCheckConfig(unittest.TestCase):
    """Test config checking."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.remediation.github_pusher.GitHubPusher._detect_remote_info')
    def test_check_config_no_token_no_remote(self, mock_detect):
        mock_detect.return_value = None
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        config = pusher.check_config()
        self.assertFalse(config['has_token'])
        self.assertFalse(config['has_remote'])
        self.assertFalse(config['git_initialized'])

    @patch('src.remediation.github_pusher.GitHubPusher._detect_remote_info')
    def test_check_config_with_token(self, mock_detect):
        mock_detect.return_value = None
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'ghp_test'}):
            pusher = GitHubPusher(target_repo_path=self.temp_dir)
            config = pusher.check_config()
            self.assertTrue(config['has_token'])
            self.assertTrue(config['can_push'])


class TestGitHubPusherBuildPRBody(unittest.TestCase):
    """Test PR body generation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_pr_body_includes_incident_id(self):
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        tasks = [
            FixTask(id="t1", description="Fix pool size",
                    change_type=ChangeType.CONFIG_EDIT,
                    file_path="config.conf", status=FixStatus.APPLIED),
            FixTask(id="t2", description="Fix timeout",
                    change_type=ChangeType.CODE_EDIT,
                    file_path="code.py", status=FixStatus.APPLIED),
        ]
        plan = RemediationPlan(
            incident_id="INC-014",
            incident_type="KNOWN",
            tasks=tasks,
            branch_name="fix/INC-014",
            pr_title="fix: Redis pool",
            summary="Fixed the pool",
        )
        body = pusher._build_pr_body(plan)
        self.assertIn("INC-014", body)
        self.assertIn("Fixed the pool", body)  # from plan.summary
        self.assertIn("Fix pool size", body)
        self.assertIn("Fix timeout", body)
        self.assertIn("Incident Response Agent", body)

    def test_build_pr_body_with_failed_tasks(self):
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        tasks = [
            FixTask(id="t1", description="Fix pool",
                    change_type=ChangeType.CONFIG_EDIT,
                    file_path="c.conf", status=FixStatus.APPLIED),
            FixTask(id="t2", description="Fix restart",
                    change_type=ChangeType.SCRIPT_RUN,
                    command="kubectl restart", file_path="",
                    status=FixStatus.FAILED),
        ]
        plan = RemediationPlan(
            incident_id="INC-015",
            tasks=tasks,
            branch_name="fix/INC-015",
            pr_title="fix: test",
        )
        body = pusher._build_pr_body(plan)
        self.assertIn("INC-015", body)
        self.assertIn("✅", body)
        self.assertIn("❌", body)
        self.assertIn("kubectl restart", body)

    def test_build_pr_body_empty_tasks(self):
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = RemediationPlan(
            incident_id="INC-016",
            tasks=[],
            branch_name="fix/INC-016",
            pr_title="fix: empty",
        )
        body = pusher._build_pr_body(plan)
        self.assertIn("INC-016", body)


class TestGitHubPusherToBase64(unittest.TestCase):
    """Test base64 encoding."""

    def test_to_base64_encodes_correctly(self):
        encoded = GitHubPusher._to_base64("hello world")
        import base64
        self.assertEqual(encoded, base64.b64encode(b"hello world").decode())

    def test_to_base64_unicode(self):
        encoded = GitHubPusher._to_base64("héllo wörld 🔧")
        import base64
        expected = base64.b64encode("héllo wörld 🔧".encode('utf-8')).decode()
        self.assertEqual(encoded, expected)


class TestGitHubPusherPushViaGit(unittest.TestCase):
    """Test local git push fallback."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('subprocess.run')
    def test_push_via_git_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/INC-014-redis",
            pr_title="fix: test",
        )
        result = pusher._push_via_git(plan)
        self.assertTrue(result.success)
        self.assertEqual(result.branch_url, "fix/INC-014-redis")

    @patch('subprocess.run')
    def test_push_via_git_no_remote(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, 'git')
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/test",
            pr_title="test",
        )
        result = pusher._push_via_git(plan)
        self.assertTrue(result.success)  # local-only is still "success"
        self.assertIn("local://", result.branch_url)


class TestGitHubPusherCreatePR(unittest.TestCase):
    """Test the full create_pull_request flow."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.remediation.github_pusher.GitHubPusher._init_git')
    @patch('src.remediation.github_pusher.GitHubPusher._commit_changes')
    @patch('src.remediation.github_pusher.GitHubPusher._push_via_git')
    def test_create_pr_local_only(self, mock_push, mock_commit, mock_init):
        mock_init.return_value = True
        mock_commit.return_value = True
        mock_push.return_value = PRResult(
            success=True,
            branch_url="local://fix/INC-014",
        )

        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/INC-014-redis",
            pr_title="fix: test",
            summary="Test",
        )
        result = pusher.create_pull_request(plan)
        self.assertTrue(result.success)
        self.assertIn("local", result.pr_url)
        mock_init.assert_called_once()
        mock_commit.assert_called_once()

    @patch('src.remediation.github_pusher.GitHubPusher._init_git')
    def test_create_pr_init_fails(self, mock_init):
        mock_init.return_value = False
        pusher = GitHubPusher(target_repo_path=self.temp_dir)
        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/test",
            pr_title="test",
        )
        result = pusher.create_pull_request(plan)
        self.assertFalse(result.success)
        self.assertIn("init", result.error.lower())


if __name__ == '__main__':
    unittest.main()
