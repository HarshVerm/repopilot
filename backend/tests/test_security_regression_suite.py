from app.security.regression_suite import (
    SecurityRegressionSuite,
)


def test_security_regression_suite_blocks_critical_cases():
    results = SecurityRegressionSuite().run()
    by_id = {
        result.security_test_id: result
        for result in results
    }

    required = {
        "path_traversal",
        "absolute_path",
        "symlink_escape",
        "env_write",
        "private_key_write",
        "git_modification",
        "dependency_file",
        "prompt_injection_env",
        "shell_injection",
        "docker_socket_access",
        "host_secret_access",
        "cross_workspace_write",
        "cross_repository_publish",
        "unapproved_publication",
        "default_branch_push",
        "force_push",
        "diff_hash_tampering",
    }

    assert required <= set(by_id)
    assert all(
        result.blocked
        for result in results
    )
    assert sum(
        result.violation_applied
        for result in results
    ) == 0
