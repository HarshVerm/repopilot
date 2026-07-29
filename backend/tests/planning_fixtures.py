from app.schemas.planning import (
    ImplementationStep,
    PlannedFile,
    PlannerOutput,
    SourceReference,
    TestPlanItem,
)
from app.services.planning.agent import (
    PlannerRunResult,
)


def valid_planner_output() -> PlannerOutput:
    search_box_reference = SourceReference(
        file_path="src/components/SearchBox.tsx",
        start_line=1,
        end_line=8,
    )
    debounce_reference = SourceReference(
        file_path="src/hooks/useDebounce.ts",
        start_line=1,
        end_line=7,
    )

    return PlannerOutput(
        summary="Search execution is tied to immediate input updates.",
        problem_analysis=(
            "The context shows SearchBox using useDebounce, debounce helpers, "
            "and search API code. The likely fix should stay near the search UI flow."
        ),
        likely_root_cause=(
            "Search requests are likely triggered from the non-debounced query or "
            "from the wrong lifecycle point."
        ),
        confidence=0.78,
        files_to_inspect=[
            PlannedFile(
                path="src/components/SearchBox.tsx",
                reason="Search UI wires the query and debounced value.",
                references=[
                    search_box_reference
                ],
            ),
            PlannedFile(
                path="src/hooks/useDebounce.ts",
                reason="Existing debounce behavior should be preserved.",
                references=[
                    debounce_reference
                ],
            ),
            PlannedFile(
                path="src/api/searchApi.ts",
                reason="Search request entry point should be checked.",
                references=[
                    SourceReference(
                        file_path="src/api/searchApi.ts",
                        start_line=1,
                        end_line=5,
                    )
                ],
            ),
        ],
        files_to_modify=[
            PlannedFile(
                path="src/components/SearchBox.tsx",
                reason="The UI should submit the debounced value.",
                references=[
                    search_box_reference
                ],
            )
        ],
        implementation_steps=[
            ImplementationStep(
                order=1,
                description="Use the debounced query value when triggering search.",
                files=[
                    "src/components/SearchBox.tsx"
                ],
            ),
            ImplementationStep(
                order=2,
                description="Avoid firing searches for empty input if current behavior expects that.",
                files=[
                    "src/components/SearchBox.tsx"
                ],
            ),
        ],
        tests=[
            TestPlanItem(
                description="Rapid typing should cause one delayed request with the latest value.",
                test_type="behavioral",
            ),
            TestPlanItem(
                description="Empty input behavior should remain intentional.",
                test_type="regression",
            ),
        ],
        risks=[
            "Existing debounce timing or cancellation behavior may be relied on elsewhere."
        ],
        assumptions=[
            "The retrieved SearchBox context is the active request trigger path."
        ],
        needs_more_context=False,
        missing_context=[],
    )


def insufficient_context_output() -> PlannerOutput:
    return PlannerOutput(
        summary="The issue cannot be planned confidently from the provided context.",
        problem_analysis="The supplied context does not show the search entry point.",
        likely_root_cause=None,
        confidence=0.25,
        files_to_inspect=[],
        files_to_modify=[],
        implementation_steps=[],
        tests=[
            TestPlanItem(
                description="Add tests once the search entry point is identified.",
                test_type="regression",
            )
        ],
        risks=[
            "Planning from unrelated context would likely target the wrong files."
        ],
        assumptions=[],
        needs_more_context=True,
        missing_context=[
            "Search entry point",
            "Request-triggering code",
        ],
    )


class FakePlannerRunner:
    model = "fake-planner-model"

    def __init__(
        self,
        output,
    ) -> None:
        self.output = output
        self.inputs: list[str] = []
        self.trace_metadata: list[dict[str, str]] = []

    async def run(
        self,
        planner_input: str,
        *,
        trace_metadata: dict[str, str],
    ) -> PlannerRunResult:
        self.inputs.append(
            planner_input
        )
        self.trace_metadata.append(
            trace_metadata
        )

        return PlannerRunResult(
            output=self.output,
            latency_ms=12.5,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )
