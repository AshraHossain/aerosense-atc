"""Resilience layer tests — retry, timeout, circuit breaker."""

import pytest
import time

from core.resilience import (
    RetryConfig,
    retry,
    timeout,
    CircuitBreaker,
    BudgetedRetry,
)


class TestRetry:
    """Retry decorator tests."""

    def test_retry_succeeds_on_first_attempt(self):
        """Successful call returns immediately."""

        @retry()
        def success():
            return "ok"

        assert success() == "ok"

    def test_retry_succeeds_after_failures(self):
        """Retry recovers from transient failures."""
        state = {"attempt": 0}

        @retry(RetryConfig(max_attempts=3, initial_delay=0.01))
        def flaky():
            state["attempt"] += 1
            if state["attempt"] < 3:
                raise ConnectionError("transient")
            return "recovered"

        assert flaky() == "recovered"
        assert state["attempt"] == 3

    def test_retry_exhausts_and_raises(self):
        """Retry raises after max attempts."""

        @retry(RetryConfig(max_attempts=2, initial_delay=0.01))
        def always_fails():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fails()

    def test_retry_config_backoff(self):
        """Retry uses exponential backoff."""
        cfg = RetryConfig(
            max_attempts=3, initial_delay=1.0, backoff_factor=2.0, jitter=False
        )
        assert cfg.delay_for_attempt(0) == 0
        assert cfg.delay_for_attempt(1) == 2.0  # 1.0 * 2^1
        assert cfg.delay_for_attempt(2) == 4.0  # 1.0 * 2^2


class TestCircuitBreaker:
    """Circuit breaker tests."""

    def test_circuit_breaker_starts_closed(self):
        """Circuit breaker is initially CLOSED."""
        cb = CircuitBreaker()
        assert cb.state == "CLOSED"

    def test_circuit_breaker_opens_after_failures(self):
        """Circuit opens after exceeding failure threshold."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        assert cb.state == "CLOSED"
        cb.record_failure()
        assert cb.state == "OPEN"

    def test_circuit_breaker_allows_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after timeout."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.1)
        cb.record_failure()
        assert cb.state == "OPEN"
        assert not cb.call_allowed()

        time.sleep(0.15)
        assert cb.call_allowed()
        assert cb.state == "HALF_OPEN"

    def test_circuit_breaker_closes_after_successes(self):
        """Circuit closes after successes in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout_seconds=0)
        cb.record_failure()
        cb.state = "HALF_OPEN"  # Force HALF_OPEN for testing

        cb.record_success()
        assert cb.state == "HALF_OPEN"  # Need more successes

        cb.record_success()
        assert cb.state == "CLOSED"

    def test_circuit_breaker_execute(self):
        """CircuitBreaker.execute() delegates to wrapped function."""
        cb = CircuitBreaker()
        result = cb.execute(lambda: "ok")
        assert result == "ok"

    def test_circuit_breaker_raises_when_open(self):
        """CircuitBreaker raises when OPEN and timeout not elapsed."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=10)
        cb.record_failure()

        with pytest.raises(RuntimeError, match="OPEN"):
            cb.execute(lambda: "ok")


class TestBudgetedRetry:
    """Budgeted retry tests."""

    def test_budgeted_retry_succeeds(self):
        """BudgetedRetry succeeds within budget."""
        br = BudgetedRetry(total_budget_seconds=1.0)
        result = br.execute(lambda: "ok", delay_between_attempts=0.01)
        assert result == "ok"

    def test_budgeted_retry_exhausts_budget(self):
        """BudgetedRetry raises TimeoutError when budget exhausted."""
        br = BudgetedRetry(total_budget_seconds=0.1)

        def always_fails():
            raise ValueError("fail")

        with pytest.raises(TimeoutError, match="budget exhausted"):
            br.execute(always_fails, delay_between_attempts=0.05)

    def test_budgeted_retry_recovers_in_time(self):
        """BudgetedRetry recovers if success happens before budget expires."""
        br = BudgetedRetry(total_budget_seconds=0.5)
        state = {"attempt": 0}

        def flaky():
            state["attempt"] += 1
            if state["attempt"] < 2:
                raise ValueError("transient")
            return "recovered"

        result = br.execute(flaky, delay_between_attempts=0.05)
        assert result == "recovered"
