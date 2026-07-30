# Module purpose: Implement editor behavior for the change-set domain.

import os
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.changes.policy import (
    PathPolicyError,
    validate_creatable_path,
    validate_editable_path,
)


# Purpose: Signal patch security failures.
class PatchSecurityError(ValueError):
    pass


# Purpose: Encapsulate repo pilot patch editor behavior for the change-set domain.
class RepoPilotPatchEditor:
    # Purpose: Initialize repo pilot patch editor state and dependencies.
    def __init__(
        self,
        *,
        repository_path: Path,
        allowed_files: set[str],
        creatable_files: set[str] | None = None,
        max_file_size: int = settings.max_editable_file_size,
    ) -> None:
        self.repository_path = repository_path
        requested_creatable_files = (
            creatable_files or set()
        )
        if not requested_creatable_files.issubset(
            allowed_files
        ):
            raise PatchSecurityError(
                "Creation scope must be a subset of the approved file scope"
            )
        self.creatable_files = (
            requested_creatable_files
        )
        self.modifiable_files = (
            allowed_files
            - self.creatable_files
        )
        self.allowed_files = (
            self.modifiable_files
            | self.creatable_files
        )
        self.max_file_size = max_file_size
        self.operations_requested = 0
        self.operations_accepted = 0
        self.operations_rejected = 0

    # Purpose: Validate path for the change-set workflow.
    def validate_path(
        self,
        path: str,
    ) -> Path:
        try:
            return validate_editable_path(
                repository_path=self.repository_path,
                requested_path=path,
                allowed_files=self.modifiable_files,
                max_file_size=self.max_file_size,
            )
        except PathPolicyError as exc:
            raise PatchSecurityError(
                str(exc)
            ) from exc

    # Purpose: Validate create path for the change-set workflow.
    def validate_create_path(
        self,
        path: str,
    ) -> Path:
        try:
            return validate_creatable_path(
                repository_path=self.repository_path,
                requested_path=path,
                allowed_files=self.creatable_files,
            )
        except PathPolicyError as exc:
            raise PatchSecurityError(
                str(exc)
            ) from exc

    # Purpose: Validate created path for the change-set workflow.
    def validate_created_path(
        self,
        path: str,
    ) -> Path:
        try:
            return validate_editable_path(
                repository_path=self.repository_path,
                requested_path=path,
                allowed_files=self.creatable_files,
                max_file_size=self.max_file_size,
            )
        except PathPolicyError as exc:
            raise PatchSecurityError(
                str(exc)
            ) from exc

    # Purpose: Read file for the change-set workflow.
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

    # Purpose: Update file for the change-set workflow.
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

    # Purpose: Create file for the change-set workflow.
    def create_file(
        self,
        *,
        path: str,
        content: str,
    ) -> dict:
        self.operations_requested += 1

        created_path: Path | None = None
        try:
            created_path = self.validate_create_path(
                path
            )
            encoded = content.encode(
                "utf-8"
            )

            if len(encoded) > self.max_file_size:
                raise PatchSecurityError(
                    "New file exceeds editable size limit"
                )

            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
            )
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW

            descriptor: int | None = os.open(
                created_path,
                flags,
                0o666,
            )
            try:
                with os.fdopen(
                    descriptor,
                    "wb",
                ) as file:
                    descriptor = None
                    file.write(encoded)
            except Exception:
                if created_path.exists():
                    created_path.unlink()
                raise
            finally:
                if descriptor is not None:
                    os.close(descriptor)

            self.validate_created_path(
                path
            )
            self.operations_accepted += 1
            return {
                "path": path,
                "created": True,
            }
        except Exception:
            self.operations_rejected += 1
            raise

    # Purpose: Delete file for the change-set workflow.
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

    # Purpose: Handle rename file for the change-set workflow.
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
