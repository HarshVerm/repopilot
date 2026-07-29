from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.models.change_set import ChangeSet
from app.db.session import get_db
from app.schemas.execution import (
    ExecutionRunResponse,
)
from app.services.sandbox.docker import (
    DockerSandbox,
)
from app.services.sandbox.manager import (
    ExecutionService,
    serialize_execution_run,
)
from app.services.sandbox.policy import (
    InvalidChangeSetStateError,
    WorkspaceStateMismatchError,
)
from app.services.hardening.rate_limit import (
    enforce_rate_limit,
)
from app.services.tasks.locking import (
    TaskOperationConflict,
)
from app.services.auth.authorization import authorize_task
from app.services.auth.service import (
    AuthContext,
    get_optional_auth_context,
    validate_csrf_tokens,
)


router = APIRouter(
    tags=["execution"],
)


def get_sandbox_runtime():
    return DockerSandbox()


@router.post(
    "/change-sets/{change_set_id}/execute",
    response_model=ExecutionRunResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "sandbox"
            )
        )
    ],
)
async def execute_change_set(
    change_set_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    sandbox=Depends(get_sandbox_runtime),
):
    try:
        service = ExecutionService(
            sandbox=sandbox
        )
        change_set = await db.get(
            ChangeSet,
            change_set_id,
        )

        if change_set is None:
            raise HTTPException(
                status_code=404,
                detail="ChangeSet not found",
            )
        await authorize_task(
            task_id=change_set.task_id,
            auth=auth,
            db=db,
        )
        if auth is not None:
            validate_csrf_tokens(
                request=request,
                context=auth,
            )

        repository_path = (
            WORKSPACES_DIR
            / change_set.workspace_id
            / "repository"
        )
        run = await service.execute_change_set(
            change_set_id=change_set_id,
            repository_path=repository_path,
            db=db,
        )
    except HTTPException:
        raise
    except InvalidChangeSetStateError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except WorkspaceStateMismatchError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except TaskOperationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return serialize_execution_run(
        run
    )


@router.get(
    "/execution-runs/{execution_run_id}",
    response_model=ExecutionRunResponse,
)
async def get_execution_run(
    execution_run_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    run = await ExecutionService().get_execution_run(
        execution_run_id=execution_run_id,
        db=db,
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="ExecutionRun not found",
        )
    await authorize_task(
        task_id=run.task_id,
        auth=auth,
        db=db,
    )

    return serialize_execution_run(
        run
    )
