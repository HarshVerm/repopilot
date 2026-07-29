import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.hardening.limits import (
    validate_startup_configuration,
)
from app.services.workspace.manager import (
    WORKSPACES_DIR,
)


@dataclass(frozen=True)
class ReadinessCheck:
    status: str
    details: str | None = None


class ReadinessService:
    async def check(
        self,
        *,
        db: AsyncSession,
        docker_required: bool = True,
    ) -> dict[str, Any]:
        checks = {
            "database": await self.check_database(
                db
            ),
            "workspace": self.check_directory(
                WORKSPACES_DIR,
                create=True,
            ),
            "sandbox": self.check_directory(
                settings.sandbox_root,
                create=True,
            ),
            "configuration": self.check_configuration(),
        }

        if docker_required:
            checks["docker"] = await self.check_docker()
        else:
            checks["docker"] = ReadinessCheck(
                status="skipped",
                details="Docker check disabled by caller",
            )

        serialized = {
            name: {
                "status": check.status,
                "details": check.details,
            }
            for name, check in checks.items()
        }
        ready = all(
            check.status
            in {
                "ok",
                "skipped",
            }
            for check in checks.values()
        )

        return {
            "status": (
                "ready"
                if ready
                else "not_ready"
            ),
            "checks": serialized,
        }

    async def check_database(
        self,
        db: AsyncSession,
    ) -> ReadinessCheck:
        try:
            await db.execute(
                text("select 1")
            )
        except Exception as exc:
            return ReadinessCheck(
                status="error",
                details=exc.__class__.__name__,
            )

        return ReadinessCheck(
            status="ok"
        )

    def check_directory(
        self,
        path: Path,
        *,
        create: bool,
    ) -> ReadinessCheck:
        try:
            if create:
                path.mkdir(
                    parents=True,
                    exist_ok=True,
                )

            if not path.exists():
                return ReadinessCheck(
                    status="error",
                    details="path does not exist",
                )
            if not path.is_dir():
                return ReadinessCheck(
                    status="error",
                    details="path is not a directory",
                )
            probe = path / ".repopilot-readiness"
            probe.write_text(
                "ok",
                encoding="utf-8",
            )
            probe.unlink()
        except Exception as exc:
            return ReadinessCheck(
                status="error",
                details=exc.__class__.__name__,
            )

        return ReadinessCheck(
            status="ok"
        )

    def check_configuration(
        self,
    ) -> ReadinessCheck:
        try:
            validate_startup_configuration()
        except Exception as exc:
            return ReadinessCheck(
                status="error",
                details=str(exc),
            )

        return ReadinessCheck(
            status="ok"
        )

    async def check_docker(
        self,
    ) -> ReadinessCheck:
        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                "version",
                "--format",
                "{{.Server.Version}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=settings.readiness_check_timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.communicate()
                return ReadinessCheck(
                    status="error",
                    details="docker check timed out",
                )

            if process.returncode != 0:
                return ReadinessCheck(
                    status="error",
                    details=(
                        stderr.decode(
                            "utf-8",
                            errors="ignore",
                        ).strip()
                        or stdout.decode(
                            "utf-8",
                            errors="ignore",
                        ).strip()
                        or "docker unavailable"
                    ),
                )
        except FileNotFoundError:
            return ReadinessCheck(
                status="error",
                details="docker executable is not available",
            )
        except subprocess.SubprocessError as exc:
            return ReadinessCheck(
                status="error",
                details=exc.__class__.__name__,
            )

        return ReadinessCheck(
            status="ok"
        )
