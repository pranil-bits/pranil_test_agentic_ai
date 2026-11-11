"""Read-only investigation tools bound to one scenario. They never change code or deploy."""


def make_tools(s):
    """Return tool functions (with docstrings, used by Ollama to build tool schemas)."""

    def get_pipeline_status() -> dict:
        """Get the failed pipeline run: run id, branch, overall status, failed stage, last successful commit and recent run history."""
        return {**s["pipeline"], "last_success_sha": s["history"]["last_success_sha"],
                "recent_runs": s["history"]["recent_runs"]}

    def read_build_logs() -> dict:
        """Read the raw build, test and deploy log lines of the failed pipeline run."""
        return {"log_lines": s["logs"].splitlines()}

    def get_test_results() -> dict:
        """Get unit test results: totals, failing test ids, error messages, the source file each test covers, and tests known to be flaky."""
        t = s["tests"]
        return {**t, "known_flaky_tests": s["history"]["flaky_tests"]}

    def get_recent_change_summary() -> dict:
        """Get commits since the last successful run: sha, author, message and files changed."""
        return {"commits": s["changes"]}

    def get_dependency_info() -> dict:
        """Get dependency changes, unresolved or unavailable packages, and compatibility warnings."""
        return s["dependencies"]

    def get_deployment_health() -> dict:
        """Get post-deployment health check results: whether checks ran, HTTP status, retries, error and environment."""
        return s["health"]

    return [get_pipeline_status, read_build_logs, get_test_results,
            get_recent_change_summary, get_dependency_info, get_deployment_health]
