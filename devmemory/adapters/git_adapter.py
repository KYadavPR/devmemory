"""GitAdapter for DevMemory using GitPython.

Handles commit inspection, diff calculation, branch detection, and safe restores.
"""

import os
from typing import Optional, List, Dict, Any
import git


class GitAdapter:
    """Encapsulates git repository operations via GitPython."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._repo: Optional[git.Repo] = None

    @property
    def repo(self) -> git.Repo:
        if self._repo is None:
            self._repo = git.Repo(self.repo_path)
        return self._repo

    def is_git_repo(self) -> bool:
        """Check if target path is an initialized git repository."""
        try:
            _ = self.repo.head
            return True
        except (git.InvalidGitRepositoryError, git.NoSuchPathError, TypeError):
            return False
        except Exception:
            return os.path.exists(os.path.join(self.repo_path, ".git"))

    def get_head_commit(self) -> Optional[Dict[str, Any]]:
        """Get HEAD commit details."""
        try:
            commit = self.repo.head.commit
            parent_sha = commit.parents[0].hexsha if commit.parents else None
            return {
                "sha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "message": commit.message.strip(),
                "author": str(commit.author),
                "timestamp": commit.committed_datetime.isoformat(),
                "parent": parent_sha,
            }
        except Exception:
            return None

    def get_diff_stats(self, commit_a: Optional[str], commit_b: Optional[str]) -> Dict[str, Any]:
        """Compute diff statistics (files, additions, deletions, diff text) between two commits."""
        default_res = {
            "files": [],
            "additions": 0,
            "deletions": 0,
            "diff": "",
        }
        if not commit_b:
            return default_res

        try:
            if not commit_a:
                try:
                    diff_text = self.repo.git.show(commit_b, format="", stat=False)
                    numstat = self.repo.git.show(commit_b, format="", numstat=True)
                except Exception:
                    diff_text = ""
                    numstat = ""
            else:
                diff_text = self.repo.git.diff(commit_a, commit_b)
                numstat = self.repo.git.diff(commit_a, commit_b, numstat=True)

            files: List[str] = []
            additions = 0
            deletions = 0

            for line in numstat.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) == 3:
                    add = int(parts[0]) if parts[0] != "-" else 0
                    rem = int(parts[1]) if parts[1] != "-" else 0
                    additions += add
                    deletions += rem
                    files.append(parts[2].strip())

            return {
                "files": files,
                "additions": additions,
                "deletions": deletions,
                "diff": diff_text,
            }
        except Exception as e:
            return {
                "files": [],
                "additions": 0,
                "deletions": 0,
                "diff": f"Diff unavailable: {e}",
            }

    def get_diff_text(self, commit_a: str, commit_b: str) -> str:
        """Get raw diff text between two commits."""
        try:
            return self.repo.git.diff(commit_a, commit_b)
        except Exception as e:
            return f"Diff error: {e}"

    def get_branch(self) -> str:
        """Return the active branch name or 'detached'."""
        try:
            return self.repo.active_branch.name
        except (TypeError, ValueError, AttributeError):
            return "detached"
        except Exception:
            return "unknown"

    def restore_commit(self, commit_sha: str) -> str:
        """Safely restore/checkout to a commit using a dedicated recovery branch."""
        branch_name = f"devmemory-restore-{commit_sha[:8]}"
        try:
            self.repo.git.checkout(commit_sha, b=branch_name)
            return branch_name
        except Exception:
            self.repo.git.checkout(branch_name)
            return branch_name

    def get_commit_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent git commit log."""
        commits = []
        try:
            for commit in self.repo.iter_commits(max_count=limit):
                commits.append({
                    "sha": commit.hexsha,
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "timestamp": commit.committed_datetime.isoformat(),
                })
        except Exception:
            pass
        return commits
