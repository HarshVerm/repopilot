from app.db.models.task import TASK_STATUSES


CREATED = "created"
REPOSITORY_PREPARING = "repository_preparing"
REPOSITORY_READY = "repository_ready"
INDEXING = "indexing"
INDEXED = "indexed"
RETRIEVING = "retrieving"
PLANNING = "planning"
PLAN_PENDING_APPROVAL = "plan_pending_approval"
PLAN_APPROVED = "plan_approved"
PLAN_REJECTED = "plan_rejected"
CODING = "coding"
PATCH_GENERATED = "patch_generated"
TESTING = "testing"
TEST_FAILED = "test_failed"
DEBUGGING = "debugging"
VERIFICATION_PASSED = "verification_passed"
REVIEW_PENDING = "review_pending"
REVIEW_APPROVED = "review_approved"
REVIEW_REJECTED = "review_rejected"
PUBLISHING = "publishing"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"


CURRENT_STEP_BY_STATUS = {
    CREATED: 1,
    REPOSITORY_PREPARING: 2,
    REPOSITORY_READY: 2,
    INDEXING: 3,
    INDEXED: 3,
    RETRIEVING: 4,
    PLANNING: 5,
    PLAN_PENDING_APPROVAL: 5,
    PLAN_APPROVED: 5,
    PLAN_REJECTED: 5,
    CODING: 6,
    PATCH_GENERATED: 6,
    TESTING: 7,
    TEST_FAILED: 7,
    DEBUGGING: 8,
    VERIFICATION_PASSED: 7,
    REVIEW_PENDING: 9,
    REVIEW_APPROVED: 9,
    REVIEW_REJECTED: 9,
    PUBLISHING: 10,
    COMPLETED: 10,
    FAILED: 10,
    CANCELLED: 10,
}


TERMINAL_STATES = {
    COMPLETED,
    PLAN_REJECTED,
    REVIEW_REJECTED,
    FAILED,
    CANCELLED,
}


CANCELLABLE_STATES = {
    CREATED,
    REPOSITORY_PREPARING,
    REPOSITORY_READY,
    INDEXING,
    INDEXED,
    RETRIEVING,
    PLANNING,
    PLAN_PENDING_APPROVAL,
    PLAN_APPROVED,
    CODING,
    PATCH_GENERATED,
    TESTING,
    TEST_FAILED,
    DEBUGGING,
    VERIFICATION_PASSED,
    REVIEW_PENDING,
    REVIEW_APPROVED,
}


VALID_TRANSITIONS = {
    CREATED: {
        REPOSITORY_PREPARING,
        REPOSITORY_READY,
        FAILED,
        CANCELLED,
    },
    REPOSITORY_PREPARING: {
        REPOSITORY_READY,
        FAILED,
        CANCELLED,
    },
    REPOSITORY_READY: {
        INDEXING,
        RETRIEVING,
        PLANNING,
        FAILED,
        CANCELLED,
    },
    INDEXING: {
        INDEXED,
        FAILED,
        CANCELLED,
    },
    INDEXED: {
        RETRIEVING,
        PLANNING,
        FAILED,
        CANCELLED,
    },
    RETRIEVING: {
        PLANNING,
        FAILED,
        CANCELLED,
    },
    PLANNING: {
        PLAN_PENDING_APPROVAL,
        FAILED,
        CANCELLED,
    },
    PLAN_PENDING_APPROVAL: {
        PLAN_APPROVED,
        PLAN_REJECTED,
        CANCELLED,
    },
    PLAN_APPROVED: {
        CODING,
        FAILED,
        CANCELLED,
    },
    CODING: {
        PATCH_GENERATED,
        FAILED,
        CANCELLED,
    },
    PATCH_GENERATED: {
        TESTING,
        FAILED,
        CANCELLED,
    },
    TESTING: {
        VERIFICATION_PASSED,
        TEST_FAILED,
        FAILED,
        CANCELLED,
    },
    TEST_FAILED: {
        DEBUGGING,
        FAILED,
        CANCELLED,
    },
    DEBUGGING: {
        TESTING,
        VERIFICATION_PASSED,
        FAILED,
        CANCELLED,
    },
    VERIFICATION_PASSED: {
        REVIEW_PENDING,
        FAILED,
        CANCELLED,
    },
    REVIEW_PENDING: {
        REVIEW_APPROVED,
        REVIEW_REJECTED,
        CANCELLED,
    },
    REVIEW_APPROVED: {
        PUBLISHING,
        FAILED,
        CANCELLED,
    },
    PUBLISHING: {
        COMPLETED,
        FAILED,
    },
    COMPLETED: set(),
    PLAN_REJECTED: set(),
    REVIEW_REJECTED: set(),
    FAILED: set(),
    CANCELLED: set(),
}


STATE_ORDER = {
    state: index
    for index, state in enumerate(
        [
            CREATED,
            REPOSITORY_PREPARING,
            REPOSITORY_READY,
            INDEXING,
            INDEXED,
            RETRIEVING,
            PLANNING,
            PLAN_PENDING_APPROVAL,
            PLAN_APPROVED,
            CODING,
            PATCH_GENERATED,
            TESTING,
            TEST_FAILED,
            DEBUGGING,
            VERIFICATION_PASSED,
            REVIEW_PENDING,
            REVIEW_APPROVED,
            PUBLISHING,
            COMPLETED,
        ]
    )
}


class TaskTransitionError(ValueError):
    pass


class TaskConcurrencyError(RuntimeError):
    pass


class TaskStateMachine:
    def validate_transition(
        self,
        *,
        current_status: str,
        new_status: str,
    ) -> None:
        if current_status not in TASK_STATUSES:
            raise TaskTransitionError(
                f"Unknown task state: {current_status}"
            )

        if new_status not in TASK_STATUSES:
            raise TaskTransitionError(
                f"Unknown task state: {new_status}"
            )

        if new_status == current_status:
            return

        if new_status not in VALID_TRANSITIONS.get(
            current_status,
            set(),
        ):
            raise TaskTransitionError(
                f"Invalid task transition: {current_status} -> {new_status}"
            )

    def validate_reconciliation(
        self,
        *,
        current_status: str,
        new_status: str,
    ) -> None:
        if new_status == current_status:
            return

        if current_status in {
            COMPLETED,
            CANCELLED,
            PLAN_REJECTED,
            REVIEW_REJECTED,
        }:
            raise TaskTransitionError(
                f"Cannot reconcile terminal task state {current_status}"
            )

        if new_status in {
            PLAN_REJECTED,
            REVIEW_REJECTED,
            FAILED,
            COMPLETED,
        }:
            return

        if STATE_ORDER.get(
            new_status,
            -1,
        ) < STATE_ORDER.get(
            current_status,
            -1,
        ):
            raise TaskTransitionError(
                f"Cannot reconcile task backwards: {current_status} -> {new_status}"
            )

    def step_for_status(
        self,
        status: str,
    ) -> int:
        return CURRENT_STEP_BY_STATUS.get(
            status,
            1,
        )
