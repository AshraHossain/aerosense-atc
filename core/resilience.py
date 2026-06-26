"""Resilience primitives: retry logic, exponential backoff, timeout guards.

Used throughout: adapter operations, LLM calls, critical sections.
Ensures the system degrades gracefully under transient failures.
"""

import asyncio
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
    ):
        """Initialize retry config.

        Args:
            max_attempts: total number of attempts (1 = no retries)
            initial_delay: first retry delay in seconds
            max_delay: maximum delay between retries
            backoff_factor: multiply delay by this each retry
            jitter: add random noise to avoid thundering herd
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

    def delay_for_attempt(self, attempt: int) -> float:
        """Compute delay for a given attempt number (0-indexed)."""
        if attempt == 0:
            return 0
        delay = min(self.initial_delay * (self.backoff_factor ** attempt), self.max_delay)
        if self.jitter:
            import random

            delay *= 0.5 + random.random()
        return delay


def retry(config: Optional[RetryConfig] = None) -> Callable[[F], F]:
    """Decorator to retry a function on transient failures.

    Args:
        config: RetryConfig (default: 3 attempts, 1s initial, 2x backoff)

    Usage:
        @retry()
        def call_kafka():
            ...
    """
    cfg = config or RetryConfig()

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None
            for attempt in range(cfg.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < cfg.max_attempts - 1:
                        delay = cfg.delay_for_attempt(attempt)
                        time.sleep(delay)
            # All retries exhausted
            raise last_error

        return cast(F, wrapper)

    return decorator


def timeout(seconds: float) -> Callable[[F], F]:
    """Decorator to enforce a timeout on a function.

    Args:
        seconds: timeout duration

    Usage:
        @timeout(5.0)
        def call_with_timeout():
            ...

    Note: Raises TimeoutError if function exceeds duration.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import signal

            def handler(signum: int, frame: Any) -> None:
                raise TimeoutError(f"{func.__name__} exceeded {seconds}s timeout")

            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(int(seconds) + 1)  # round up to nearest second
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)  # cancel alarm
                signal.signal(signal.SIGALRM, old_handler)
            return result

        return cast(F, wrapper)

    return decorator


class CircuitBreaker:
    """Circuit breaker for fault isolation.

    Tracks failures and stops calling a service if failure rate exceeds threshold.
    States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery) → CLOSED
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: open circuit after N failures
            success_threshold: close circuit after N successes in half-open state
            timeout_seconds: time in OPEN state before trying HALF_OPEN
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds

        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0

    def record_success(self) -> None:
        """Record a successful call."""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "CLOSED"
                self.success_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

    def call_allowed(self) -> bool:
        """Check if a call is allowed given current circuit state."""
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            # Allow retry after timeout
            if time.time() - self.last_failure_time > self.timeout_seconds:
                self.state = "HALF_OPEN"
                self.success_count = 0
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False

    def execute(self, func: Callable[[], Any]) -> Any:
        """Execute a function through the circuit breaker.

        Raises RuntimeError if circuit is OPEN and not ready to retry.
        """
        if not self.call_allowed():
            raise RuntimeError(f"Circuit breaker is OPEN (service unavailable)")

        try:
            result = func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise


class BudgetedRetry:
    """Retry with a global budget (total time across all retries).

    Use when retrying is necessary but you want a hard wall-clock limit.
    """

    def __init__(self, total_budget_seconds: float = 30.0):
        """Initialize with a total budget.

        Args:
            total_budget_seconds: total time allowed for all attempts
        """
        self.total_budget_seconds = total_budget_seconds
        self.start_time = 0.0

    def execute(
        self, func: Callable[[], Any], delay_between_attempts: float = 1.0
    ) -> Any:
        """Execute with retry until budget exhausted or success.

        Args:
            func: function to retry
            delay_between_attempts: sleep duration between retries

        Returns:
            result of func() on success

        Raises:
            TimeoutError if budget exhausted
            Last exception from func() if budget exhausted
        """
        self.start_time = time.time()
        last_error = None
        attempt = 0

        while True:
            try:
                return func()
            except Exception as e:
                last_error = e
                elapsed = time.time() - self.start_time
                remaining = self.total_budget_seconds - elapsed
                if remaining <= 0:
                    raise TimeoutError(
                        f"Retry budget exhausted ({self.total_budget_seconds}s)"
                    ) from last_error
                sleep_time = min(delay_between_attempts, remaining)
                time.sleep(sleep_time)
                attempt += 1
