import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task import TaskOperationLock


class TaskOperationConflict(RuntimeError):
    pass


class TaskOperationLockService:
    async def acquire(
        self,
        *,
        task_id: uuid.UUID,
        operation: str,
        db: AsyncSession,
        owner: str | None = None,
        ttl_seconds: int = 900,
    ) -> TaskOperationLock:
        now = datetime.now(
            UTC
        )
        await db.execute(
            delete(TaskOperationLock).where(
                TaskOperationLock.expires_at <= now
            )
        )
        lock = TaskOperationLock(
            task_id=task_id,
            operation=operation,
            owner=owner or "api",
            expires_at=now
            + timedelta(
                seconds=ttl_seconds
            ),
        )
        db.add(lock)

        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise TaskOperationConflict(
                "Task already has an active operation"
            ) from exc

        await db.refresh(lock)
        return lock

    async def release(
        self,
        *,
        task_id: uuid.UUID,
        operation: str | None,
        db: AsyncSession,
    ) -> None:
        conditions = [
            TaskOperationLock.task_id == task_id
        ]

        if operation is not None:
            conditions.append(
                TaskOperationLock.operation
                == operation
            )

        await db.execute(
            delete(TaskOperationLock).where(
                *conditions
            )
        )
        await db.commit()

