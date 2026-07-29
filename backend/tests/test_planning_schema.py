import pytest
from pydantic import ValidationError

from app.schemas.planning import PlannerOutput
from app.services.planning.agent import (
    PLANNER_INSTRUCTIONS,
    create_planner_agent,
)
from tests.planning_fixtures import (
    valid_planner_output,
)


def test_planner_output_schema_accepts_valid_output():
    output = valid_planner_output()

    assert output.confidence == 0.78
    assert output.files_to_modify[0].path == "src/components/SearchBox.tsx"


def test_planner_output_schema_rejects_bad_confidence():
    data = valid_planner_output().model_dump()
    data["confidence"] = 1.5

    with pytest.raises(
        ValidationError
    ):
        PlannerOutput.model_validate(data)


def test_planner_output_schema_rejects_missing_required_field():
    data = valid_planner_output().model_dump()
    data.pop("summary")

    with pytest.raises(
        ValidationError
    ):
        PlannerOutput.model_validate(data)


def test_planner_output_schema_rejects_wrong_file_shape():
    data = valid_planner_output().model_dump()
    data["files_to_modify"] = [
        "src/components/SearchBox.tsx"
    ]

    with pytest.raises(
        ValidationError
    ):
        PlannerOutput.model_validate(data)


def test_planner_agent_has_no_tools_and_treats_content_as_untrusted():
    agent = create_planner_agent()

    assert agent.tools == []
    assert agent.handoffs == []
    assert "untrusted" in PLANNER_INSTRUCTIONS
    assert "execute shell commands" in PLANNER_INSTRUCTIONS
    assert "apply patches" in PLANNER_INSTRUCTIONS
