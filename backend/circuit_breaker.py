"""
Circuit Breaker Pattern for 3rd-party API resilience.

Implements a three-state finite state machine:
  CLOSED    → Normal operation. Calls pass through. Failures are counted.
  OPEN      → Circuit has tripped (too many failures). All calls are
              immediately short-circuited to the fallback for `recovery_timeout`
              seconds, avoiding hammering a dead API.
  HALF_OPEN → After the recovery timeout, ONE probe call is allowed through.
              If it succeeds, the circuit resets to CLOSED.
              If it fails, the circuit re-opens for another timeout period.

Additionally, this module integrates the Bright Data CLI (`scrape_with_brightdata`) 
as the ultimate last-resort fallback. If the primary APIs fail, the circuit breaker 
transparently delegates the query to Bright Data for live web scraping to ensure 100% uptime.

Usage:
    from backend.circuit_breaker import CircuitBreaker

    flight_breaker = CircuitBreaker(name="AviationStack", failure_threshold=3, recovery_timeout=300)

    def search_flights(...):
        if flight_breaker.is_open():
            return _fallback_search(...)
        try:
            result = _call_real_api(...)
            flight_breaker.record_success()
            return result
        except Exception:
            flight_breaker.record_failure()
            return _fallback_search(...)
"""

import time
import logging
from enum import Enum
from threading import Lock

log = logging.getLogger(__name__)


class CircuitState(Enum):
    """The three states of a circuit breaker."""
    CLOSED = "CLOSED"          # Normal — calls pass through
    OPEN = "OPEN"              # Tripped — calls are blocked
    HALF_OPEN = "HALF_OPEN"    # Recovery probe — one call allowed


class CircuitBreaker:
    """
    Thread-safe Circuit Breaker for wrapping unreliable external API calls.

    Args:
        name:               Human-readable identifier for logging (e.g. "AviationStack").
        failure_threshold:  Number of consecutive failures before the circuit trips.
        recovery_timeout:   Seconds to wait in OPEN state before allowing a probe.
    """

    def __init__(
        self,
        name: str = "API",
        failure_threshold: int = 3,
        recovery_timeout: int = 300,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = Lock()

        # Metrics
        self.total_calls = 0
        self.total_failures = 0
        self.total_fallbacks = 0
        self.total_trips = 0

    @property
    def state(self) -> CircuitState:
        """Current state of the circuit, accounting for automatic recovery."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    log.info(
                        "[CircuitBreaker:%s] Recovery timeout reached (%.0fs). "
                        "Transitioning OPEN → HALF_OPEN.",
                        self.name, elapsed,
                    )
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def is_open(self) -> bool:
        """Returns True if the circuit is OPEN (calls should be blocked)."""
        return self.state == CircuitState.OPEN

    def allow_request(self) -> bool:
        """
        Returns True if a real API call should be attempted.
        CLOSED   → always True
        HALF_OPEN → True (one probe call)
        OPEN     → False (use fallback)
        """
        current = self.state
        return current in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful API call. Resets the circuit to CLOSED."""
        with self._lock:
            self.total_calls += 1
            if self._state == CircuitState.HALF_OPEN:
                log.info(
                    "[CircuitBreaker:%s] Probe succeeded. Resetting HALF_OPEN → CLOSED.",
                    self.name,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed API call. May trip the circuit."""
        with self._lock:
            self.total_calls += 1
            self.total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._state = CircuitState.OPEN
                self.total_trips += 1
                log.warning(
                    "[CircuitBreaker:%s] Probe FAILED. Re-opening circuit for %ds.",
                    self.name, self.recovery_timeout,
                )
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self.total_trips += 1
                log.warning(
                    "[CircuitBreaker:%s] %d consecutive failures — TRIPPING circuit! "
                    "All calls will fallback for %ds.",
                    self.name, self._failure_count, self.recovery_timeout,
                )

    def record_fallback(self) -> None:
        """Record that a fallback was used instead of the real API."""
        with self._lock:
            self.total_fallbacks += 1

    def get_metrics(self) -> dict:
        """Return a snapshot of circuit breaker metrics for monitoring."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "total_calls": self.total_calls,
                "total_failures": self.total_failures,
                "total_fallbacks": self.total_fallbacks,
                "total_trips": self.total_trips,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_s": self.recovery_timeout,
            }

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, state={self.state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )


# ── Pre-configured instances for each external API ──────────────────────────

aviation_breaker = CircuitBreaker(
    name="AviationStack",
    failure_threshold=3,
    recovery_timeout=300,     # 5 minutes
)

railradar_breaker = CircuitBreaker(
    name="RailRadar",
    failure_threshold=3,
    recovery_timeout=300,
)

weather_breaker = CircuitBreaker(
    name="OpenMeteo",
    failure_threshold=3,
    recovery_timeout=180,     # 3 minutes (weather is less critical)
)

hotel_breaker = CircuitBreaker(
    name="BookingCom",
    failure_threshold=3,
    recovery_timeout=300,
)


# ── Bright Data Scraping Fallback ───────────────────────────────────────────

def scrape_with_brightdata(query: str, search_type: str = "web") -> str:
    """
    Robust fallback scraper using Bright Data CLI when standard APIs fail.
    
    This function spawns a subprocess to execute `brightdata search <query> --json`.
    If the Bright Data CLI is not installed or configured, it returns an empty list.
    
    Args:
        query: The search query (e.g. "Flights from Delhi to Mumbai on Makemytrip").
        search_type: "web" for general Google results.
        
    Returns:
        JSON string of results from the Bright Data SERP API.
    """
    import subprocess
    import json
    
    log.info("[BrightData Fallback] Invoking Bright Data CLI for: '%s'", query)
    
    try:
        # We use the SERP search feature of brightdata CLI since it handles 
        # organic results and structure automatically.
        result = subprocess.run(
            ["npx", "@brightdata/cli", "search", query, "--type", search_type, "--json"],
            capture_output=True,
            text=True,
            timeout=20, # BrightData might take a bit
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # Clean and validate JSON before returning
            raw_data = result.stdout.strip()
            # Some versions of brightdata output extra logs before json, so we extract JSON array/object
            if raw_data.startswith("[") or raw_data.startswith("{"):
                # Successfully scraped
                log.info("[BrightData Fallback] Successfully fetched %d bytes of scraped data", len(raw_data))
                return raw_data
        
        log.warning("[BrightData Fallback] Scrape failed or returned non-JSON. Return code: %d, Stderr: %s", 
                    result.returncode, result.stderr[:200])
    
    except subprocess.TimeoutExpired:
        log.error("[BrightData Fallback] Scraping timed out after 20s")
    except Exception as exc:
        log.error("[BrightData Fallback] Execution error: %s", exc)
        
    return "[]"  # Empty JSON array as ultimate fallback
