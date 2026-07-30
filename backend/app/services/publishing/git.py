# Module purpose: Implement git behavior for the publication domain.

import os
import shlex
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.services.changes.git import (
    GitCommandError,
    get_git_diff,
)
from app.services.publishing.authentication import (
    GitHubCredentials,
)


# Purpose: Signal git push failures.
class GitPushError(RuntimeError):
    pass


# Purpose: Encapsulate safe git publisher behavior for the publication domain.
class SafeGitPublisher:
    # Purpose: Initialize safe git publisher state and dependencies.
    def __init__(
        self,
        *,
        repository_path: Path,
    ) -> None:
        self.repository_path = repository_path

    # Purpose: Run publication for the publication workflow.
    def run(
        self,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> str:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.repository_path),
                *args,
            ],
            capture_output=True,
            check=False,
            text=True,
            env=env,
        )

        if result.returncode != 0:
            raise GitCommandError(
                sanitize_error(
                    result.stderr.strip()
                    or result.stdout.strip(),
                    secrets=secrets,
                )
            )

        return result.stdout

    # Purpose: Run with credentials for the publication workflow.
    def run_with_credentials(
        self,
        args: list[str],
        *,
        credentials: GitHubCredentials | None,
    ) -> str:
        if credentials is None:
            return self.run(
                args
            )

        with credential_env(
            credentials
        ) as (
            env,
            secrets,
        ):
            return self.run(
                args,
                env=env,
                secrets=secrets,
            )

    # Purpose: Handle current head for the publication workflow.
    def current_head(
        self,
    ) -> str:
        return self.run(
            [
                "rev-parse",
                "HEAD",
            ]
        ).strip()

    # Purpose: Handle current branch for the publication workflow.
    def current_branch(
        self,
    ) -> str:
        return self.run(
            [
                "branch",
                "--show-current",
            ]
        ).strip()

    # Purpose: Handle working tree diff for the publication workflow.
    def working_tree_diff(
        self,
    ) -> str:
        return get_git_diff(
            self.repository_path
        )

    # Purpose: Handle staged diff for the publication workflow.
    def staged_diff(
        self,
    ) -> str:
        return self.run(
            [
                "diff",
                "--cached",
                "--no-ext-diff",
                "--unified=3",
            ]
        )

    # Purpose: Handle staged files for the publication workflow.
    def staged_files(
        self,
    ) -> list[str]:
        return [
            line
            for line in self.run(
                [
                    "diff",
                    "--cached",
                    "--name-only",
                ]
            ).splitlines()
            if line
        ]

    # Purpose: Handle local branch exists for the publication workflow.
    def local_branch_exists(
        self,
        branch_name: str,
    ) -> bool:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.repository_path),
                "rev-parse",
                "--verify",
                f"refs/heads/{branch_name}",
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        return result.returncode == 0

    # Purpose: Handle switch or create branch for the publication workflow.
    def switch_or_create_branch(
        self,
        branch_name: str,
    ) -> None:
        if self.local_branch_exists(
            branch_name
        ):
            self.run(
                [
                    "checkout",
                    branch_name,
                ]
            )
            return

        self.run(
            [
                "checkout",
                "-b",
                branch_name,
            ]
        )

    # Purpose: Stage files for the publication workflow.
    def stage_files(
        self,
        paths: list[str],
    ) -> None:
        self.run(
            [
                "add",
                "--",
                *paths,
            ]
        )

    # Purpose: Handle unstage files for the publication workflow.
    def unstage_files(
        self,
        paths: list[str],
    ) -> None:
        if not paths:
            return

        self.run(
            [
                "reset",
                "--",
                *paths,
            ]
        )

    # Purpose: Handle commit for the publication workflow.
    def commit(
        self,
        *,
        subject: str,
        body: str,
    ) -> str:
        self.run(
            [
                "-c",
                "user.name=RepoPilot",
                "-c",
                "user.email=repopilot@example.com",
                "commit",
                "-m",
                subject,
                "-m",
                body,
            ]
        )

        return self.current_head()

    # Purpose: Handle commit parent for the publication workflow.
    def commit_parent(
        self,
        commit_sha: str,
    ) -> str:
        return self.run(
            [
                "rev-parse",
                f"{commit_sha}^",
            ]
        ).strip()

    # Purpose: Handle commit diff for the publication workflow.
    def commit_diff(
        self,
        *,
        base_commit_sha: str,
        commit_sha: str,
    ) -> str:
        return self.run(
            [
                "diff",
                "--no-ext-diff",
                "--unified=3",
                base_commit_sha,
                commit_sha,
            ]
        )

    # Purpose: Handle remote branch sha for the publication workflow.
    def remote_branch_sha(
        self,
        branch_name: str,
        *,
        credentials: GitHubCredentials | None = None,
    ) -> str | None:
        output = self.run_with_credentials(
            [
                "ls-remote",
                "--heads",
                "origin",
                branch_name,
            ],
            credentials=credentials,
        )

        if not output.strip():
            return None

        return output.split()[0]

    # Purpose: Handle push branch for the publication workflow.
    def push_branch(
        self,
        *,
        branch_name: str,
        credentials: GitHubCredentials | None,
    ) -> None:
        try:
            self.run_with_credentials(
                [
                    "push",
                    "origin",
                    branch_name,
                ],
                credentials=credentials,
            )
        except GitCommandError as exc:
            raise GitPushError(
                str(exc)
            ) from exc

    # Purpose: Handle remote config for the publication workflow.
    def remote_config(
        self,
    ) -> str:
        return self.run(
            [
                "remote",
                "-v",
            ]
        )


# Purpose: Handle credential env for the publication workflow.
@contextmanager
def credential_env(
    credentials: GitHubCredentials | None,
) -> Iterator[tuple[dict[str, str] | None, tuple[str, ...]]]:
    if credentials is None:
        yield None, ()
        return

    with askpass_script(
        credentials
    ) as script_path:
        env = {
            **os.environ,
            "GIT_ASKPASS": str(script_path),
            "GIT_TERMINAL_PROMPT": "0",
        }

        yield env, (credentials.token,)


# Purpose: Handle askpass script for the publication workflow.
@contextmanager
def askpass_script(
    credentials: GitHubCredentials,
) -> Iterator[Path]:
    fd, path = tempfile.mkstemp(
        prefix="repopilot-askpass-",
        text=True,
    )
    script_path = Path(path)

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file:
            file.write("#!/bin/sh\n")
            file.write('case "$1" in\n')
            file.write(
                "*Username*) printf '%s\\n' "
                f"{shlex.quote(credentials.username)} ;;\n"
            )
            file.write(
                "*) printf '%s\\n' "
                f"{shlex.quote(credentials.token)} ;;\n"
            )
            file.write("esac\n")

        script_path.chmod(
            stat.S_IRUSR | stat.S_IXUSR
        )
        yield script_path
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass


# Purpose: Sanitize error for the publication workflow.
def sanitize_error(
    message: str,
    *,
    secrets: tuple[str, ...] = (),
) -> str:
    sanitized = message

    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(
                secret,
                "[REDACTED]",
            )

    return sanitized
