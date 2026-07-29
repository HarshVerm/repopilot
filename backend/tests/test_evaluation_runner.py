import asyncio
import uuid
from pathlib import Path

from app.db.models.evaluation_run import EvaluationRun
from app.db.session import AsyncSessionLocal
from app.evaluation.runner import (
    EvaluationRunner,
    load_persisted_results,
    persist_task_result,
)
from app.evaluation.models import (
    EvaluationTaskResultData,
)


def test_evaluation_dry_run_writes_json_and_markdown_reports(
    tmp_path: Path,
):
    result = asyncio.run(
        EvaluationRunner().run(
            suite_version="repopilot-eval-v1",
            output_dir=tmp_path,
            dry_run=True,
        )
    )

    assert Path(
        result["paths"]["json"]
    ).exists()
    assert Path(
        result["paths"]["markdown"]
    ).exists()
    assert result["report"]["dry_run"] is True
    assert result["report"]["live_run"] is False
    assert result["report"]["suite"]["task_count"] == 20


def test_evaluation_result_persistence_round_trip():
    async def run_test():
        async with AsyncSessionLocal() as db:
            run = EvaluationRun(
                suite_name="repopilot-eval",
                suite_version="repopilot-eval-v1",
                status="running",
                total_tasks=1,
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

            await persist_task_result(
                evaluation_run_id=run.id,
                result=EvaluationTaskResultData(
                    evaluation_task_id="eval-test",
                    status="passed",
                    difficulty="easy",
                    category="test",
                    final_success=True,
                    retrieval_recall_at_5=1.0,
                ),
                db=db,
            )
            loaded = await load_persisted_results(
                evaluation_run_id=run.id,
                db=db,
            )

            assert len(loaded) == 1
            assert loaded[0].evaluation_task_id == "eval-test"
            assert loaded[0].final_success is True

    asyncio.run(
        run_test()
    )
