import os
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.changes.policy import (
    PathPolicyError,
    validate_editable_path,
)


class PatchSecurityError(ValueError):
    pass


class RepoPilotPatchEditor:
    def __init__(
        self,
        *,
        repository_path: Path,
        allowed_files: set[str],
        max_file_size: int = settings.max_editable_file_size,
    ) -> None:
        self.repository_path = repository_path
        self.allowed_files = allowed_files
        self.max_file_size = max_file_size
        self.operations_requested = 0
        self.operations_accepted = 0
        self.operations_rejected = 0

    def validate_path(
        self,
        path: str,
    ) -> Path:
        try:
            return validate_editable_path(
                repository_path=self.repository_path,
                requested_path=path,
                allowed_files=self.allowed_files,
                max_file_size=self.max_file_size,
            )
        except PathPolicyError as exc:
            raise PatchSecurityError(
                str(exc)
            ) from exc

    def read_file(
        self,
        path: str,
    ) -> str:
        resolved_path = self.validate_path(
            path
        )

        return resolved_path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

    def update_file(
        self,
        *,
        path: str,
        content: str,
    ) -> dict:
        self.operations_requested += 1

        try:
            resolved_path = self.validate_path(
                path
            )
            encoded = content.encode(
                "utf-8"
            )

            if len(encoded) > self.max_file_size:
                raise PatchSecurityError(
                    "Updated file exceeds editable size limit"
                )

            temporary_path = resolved_path.with_name(
                f".{resolved_path.name}.repopilot-{uuid.uuid4().hex}.tmp"
            )

            try:
                temporary_path.write_bytes(encoded)
                os.replace(
                    temporary_path,
                    resolved_path,
                )
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

            self.validate_path(
                path
            )
            self.operations_accepted += 1

            return {
                "path": path,
                "updated": True,
            }
        except Exception:
            self.operations_rejected += 1
            raise

    def create_file(
        self,
        *,
        path: str,
        content: str,
    ) -> dict:
        self.operations_requested += 1
        self.operations_rejected += 1
        raise PatchSecurityError(
            "Creating files is disabled in Step 6"
        )

    def delete_file(
        self,
        *,
        path: str,
    ) -> dict:
        self.operations_requested += 1
        self.operations_rejected += 1
        raise PatchSecurityError(
            "Deleting files is disabled in Step 6"
        )

    def rename_file(
        self,
        *,
        source_path: str,
        destination_path: str,
    ) -> dict:
        self.operations_requested += 1
        self.operations_rejected += 1
        raise PatchSecurityError(
            "Renaming files is disabled in Step 6"
        )
