"""
RPC retry utility to handle Infura rate limiting (429 errors).
Monkey-patches boa's RPC client to add:
1. Rate limiting/throttling to PREVENT hitting limits
2. Retry logic with exponential backoff for when limits are hit

Based on Infura's limits (2024):
- Free tier: 2,000 credits/second, 6M credits/day
- We throttle to stay well under these limits
"""

import functools
import os
import time
from threading import Lock
from typing import Any, Callable

# Try to import boa modules
try:
    import boa.rpc as rpc_module
except ImportError:
    rpc_module = None

try:
    import boa.vm.fork as fork_module
except ImportError:
    fork_module = None

# Rate limiting state
_rate_limiter_lock = Lock()
_last_call_time = 0.0
_call_count = 0
_call_times = []
# Default: 0.005 seconds = max 200 calls/second (very conservative, well under Infura's 2000/sec free tier limit)
# Can be adjusted via environment variable RPC_THROTTLE_DELAY (in seconds)
_min_delay_between_calls = float(os.environ.get("RPC_THROTTLE_DELAY", "0.005"))
_enable_debug = os.environ.get("RPC_DEBUG", "false").lower() == "true"


def rate_limit_throttle():
    """
    Throttle RPC calls to prevent hitting rate limits.
    Ensures minimum delay between calls to stay under Infura's limits.
    """
    global _last_call_time, _call_count, _call_times

    with _rate_limiter_lock:
        current_time = time.time()
        time_since_last_call = current_time - _last_call_time

        if time_since_last_call < _min_delay_between_calls:
            sleep_time = _min_delay_between_calls - time_since_last_call
            time.sleep(sleep_time)

        _last_call_time = time.time()
        _call_count += 1

        # Track call times for rate calculation (keep last 100)
        _call_times.append(_last_call_time)
        if len(_call_times) > 100:
            _call_times.pop(0)

        # Debug output every 100 calls
        if _enable_debug and _call_count % 100 == 0:
            if len(_call_times) >= 2:
                time_span = _call_times[-1] - _call_times[0]
                calls_per_sec = (
                    (len(_call_times) - 1) / time_span if time_span > 0 else 0
                )
                print(
                    f"RPC call #{_call_count}: ~{calls_per_sec:.1f} calls/sec (last 100 calls)"
                )


def retry_with_backoff(
    max_retries: int = 5,
    initial_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_status_codes: tuple = (429, 503, 504),
):
    """
    Decorator to retry RPC calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries
        backoff_factor: Multiplier for exponential backoff
        retryable_status_codes: HTTP status codes that should trigger retries
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # First, throttle to prevent hitting rate limits
            rate_limit_throttle()

            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if it's a retryable HTTP error
                    status_code = None
                    if hasattr(e, "response") and hasattr(e.response, "status_code"):
                        status_code = e.response.status_code
                    elif hasattr(e, "status_code"):
                        status_code = e.status_code

                    # Check error message for rate limiting indicators
                    error_str = str(e)
                    is_rate_limit = (
                        status_code in retryable_status_codes
                        or "429" in error_str
                        or "Too Many Requests" in error_str
                        or "rate limit" in error_str.lower()
                        or "Rate limit" in error_str
                    )

                    # Only retry on specific status codes or if we haven't exceeded max retries
                    if attempt < max_retries and is_rate_limit:
                        print(
                            f"RPC call failed (attempt {attempt + 1}/{max_retries + 1}): {error_str[:100]}"
                        )
                        print(f"Retrying in {delay:.2f} seconds...")
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                        continue

                    # If not retryable or max retries exceeded, raise
                    raise

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def patch_rpc_client():
    """
    Monkey-patch boa's RPC client to add retry logic.
    This should be called before boa.fork().
    """
    patched = False

    # Debug: Check what we can import
    if _enable_debug:
        print(f"Debug: rpc_module = {rpc_module}")
        print(f"Debug: fork_module = {fork_module}")
        if rpc_module:
            print(
                f"Debug: rpc_module has RPCClient: {hasattr(rpc_module, 'RPCClient')}"
            )
        if fork_module:
            print(f"Debug: fork_module has ForkDB: {hasattr(fork_module, 'ForkDB')}")

    # Try to patch RPCClient.fetch method
    if rpc_module is not None:
        if hasattr(rpc_module, "RPCClient"):
            original_fetch = rpc_module.RPCClient.fetch

            @retry_with_backoff(
                max_retries=5, initial_delay=2.0, max_delay=60.0, backoff_factor=2.0
            )
            def patched_fetch(self, method, params):
                return original_fetch(self, method, params)

            rpc_module.RPCClient.fetch = patched_fetch
            patched = True
            print("✓ Patched RPCClient.fetch with retry logic")

        # Also try to patch standalone fetch function if it exists
        if hasattr(rpc_module, "fetch") and callable(
            getattr(rpc_module, "fetch", None)
        ):
            original_fetch_func = rpc_module.fetch

            @retry_with_backoff(
                max_retries=5, initial_delay=2.0, max_delay=60.0, backoff_factor=2.0
            )
            def patched_fetch_func(*args, **kwargs):
                return original_fetch_func(*args, **kwargs)

            rpc_module.fetch = patched_fetch_func
            patched = True
            print("✓ Patched rpc.fetch with retry logic")

    # Try to patch the fork module's ForkDB.fetch method
    # The traceback shows ForkDB.fetch() calls self._rpc.fetch()
    if fork_module is not None:
        if hasattr(fork_module, "ForkDB"):
            original_forkdb_fetch = fork_module.ForkDB.fetch

            @retry_with_backoff(
                max_retries=5, initial_delay=2.0, max_delay=60.0, backoff_factor=2.0
            )
            def patched_forkdb_fetch(self, method, params):
                return original_forkdb_fetch(self, method, params)

            fork_module.ForkDB.fetch = patched_forkdb_fetch
            patched = True
            print("✓ Patched ForkDB.fetch with retry logic")

    # FALLBACK: Patch requests at the Session level for RPC calls only
    # This is more aggressive but should work if the above patches fail
    try:
        import requests

        original_session_request = requests.Session.request

        def patched_session_request(self, method, url, *args, **kwargs):
            # Only throttle/retry for Infura URLs
            if "infura.io" in str(url):
                # Throttle before the request
                rate_limit_throttle()

                # Retry logic
                delay = 3.0  # Start with longer delay
                max_retries = 5
                last_exception = None

                for attempt in range(max_retries + 1):
                    try:
                        response = original_session_request(
                            self, method, url, *args, **kwargs
                        )
                        # Check for 429 status - handle before raise_for_status() is called
                        if response.status_code == 429:
                            if attempt < max_retries:
                                error_msg = f"429 Too Many Requests (attempt {attempt + 1}/{max_retries + 1})"
                                print(f"RPC call failed: {error_msg}")
                                print(f"Retrying in {delay:.2f} seconds...")
                                time.sleep(delay)
                                delay = min(delay * 2.0, 60.0)
                                continue
                            else:
                                # Max retries exceeded, raise the error
                                response.raise_for_status()
                        return response
                    except requests.exceptions.HTTPError as e:
                        last_exception = e
                        if e.response and e.response.status_code == 429:
                            if attempt < max_retries:
                                print(
                                    f"RPC call failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                                )
                                print(f"Retrying in {delay:.2f} seconds...")
                                time.sleep(delay)
                                delay = min(delay * 2.0, 60.0)
                                continue
                        raise
                    except Exception as e:
                        # For non-HTTP errors, check if it's rate limit related
                        error_str = str(e)
                        if "429" in error_str or "Too Many Requests" in error_str:
                            if attempt < max_retries:
                                print(
                                    f"RPC call failed (attempt {attempt + 1}/{max_retries + 1}): {error_str[:100]}"
                                )
                                print(f"Retrying in {delay:.2f} seconds...")
                                time.sleep(delay)
                                delay = min(delay * 2.0, 60.0)
                                continue
                        raise

                if last_exception:
                    raise last_exception
            else:
                # Not an Infura URL, just pass through
                return original_session_request(self, method, url, *args, **kwargs)

        requests.Session.request = patched_session_request
        patched = True
        print("✓ Patched requests.Session.request for Infura URLs (fallback)")
    except ImportError:
        pass
    except Exception as e:
        if _enable_debug:
            print(f"Could not patch requests: {e}")

    if not patched:
        print("Warning: Could not patch RPC client. Retry logic may not work.")
        print(
            "  This means RPC calls are NOT being throttled - you may hit rate limits!"
        )
    else:
        print("RPC rate limiting and retry logic enabled.")
        print(
            f"  - Throttling: {1/_min_delay_between_calls:.0f} calls/second max (Infura free tier: 2000/sec)"
        )
        print(
            "  - Will retry on 429 errors with exponential backoff (3s, 6s, 12s, 24s, 48s)"
        )
        if _enable_debug:
            print("  - Debug mode enabled: will show call rate statistics")


def patch_rpc_client_after_fork():
    """
    Patch the RPC client after boa.fork() has been called.
    This patches the actual RPC client instance used by the fork.
    Call this after boa.fork() if the pre-fork patching didn't work.
    """
    try:
        import boa

        # Try multiple ways to find the ForkDB instance
        fork_db = None

        # Method 1: Check boa.env._fork_db
        if hasattr(boa, "env") and hasattr(boa.env, "_fork_db"):
            fork_db = boa.env._fork_db

        # Method 2: Check boa.env.evm.state._account_db (ForkDB is the account_db)
        if fork_db is None and hasattr(boa, "env") and hasattr(boa.env, "evm"):
            if hasattr(boa.env.evm, "state") and hasattr(
                boa.env.evm.state, "_account_db"
            ):
                account_db = boa.env.evm.state._account_db
                # Check if it's a ForkDB (has _rpc attribute)
                if hasattr(account_db, "_rpc"):
                    fork_db = account_db

        # Method 3: Check boa.env.evm.state.account_db (without underscore)
        if fork_db is None and hasattr(boa, "env") and hasattr(boa.env, "evm"):
            if hasattr(boa.env.evm, "state") and hasattr(
                boa.env.evm.state, "account_db"
            ):
                account_db = boa.env.evm.state.account_db
                if hasattr(account_db, "_rpc"):
                    fork_db = account_db

        if fork_db is not None:
            if hasattr(fork_db, "_rpc") and hasattr(fork_db._rpc, "fetch"):
                original_fetch = fork_db._rpc.fetch

                # Check if already patched (has our wrapper attributes)
                if hasattr(original_fetch, "__wrapped__"):
                    print("RPC client already patched")
                    return True

                @retry_with_backoff(
                    max_retries=5, initial_delay=2.0, max_delay=60.0, backoff_factor=2.0
                )
                def patched_fetch(method, params):
                    return original_fetch(method, params)

                fork_db._rpc.fetch = patched_fetch
                print("✓ Patched fork RPC client with rate limiting and retry logic")
                print(f"  RPC client type: {type(fork_db._rpc)}")
                print(f"  ForkDB type: {type(fork_db)}")
                return True
            else:
                print(
                    f"Debug: fork_db found but structure issue - has _rpc: {hasattr(fork_db, '_rpc')}, "
                    f"has fetch: {hasattr(fork_db._rpc, 'fetch') if hasattr(fork_db, '_rpc') else False}"
                )
        else:
            # Debug: print what we can find
            debug_info = []
            if hasattr(boa, "env"):
                debug_info.append("has env")
                if hasattr(boa.env, "_fork_db"):
                    debug_info.append("has _fork_db")
                if hasattr(boa.env, "evm"):
                    debug_info.append("has evm")
                    if hasattr(boa.env.evm, "state"):
                        debug_info.append("has state")
                        if hasattr(boa.env.evm.state, "_account_db"):
                            debug_info.append("has _account_db")
                        if hasattr(boa.env.evm.state, "account_db"):
                            debug_info.append("has account_db")
            print(f"Debug: Could not find ForkDB. Found: {', '.join(debug_info)}")

    except Exception as e:
        import traceback

        print(f"Could not patch RPC client after fork: {e}")
        if _enable_debug:
            print(f"Traceback: {traceback.format_exc()}")

    return False


def get_rpc_stats():
    """
    Get statistics about RPC calls made so far.
    Returns a dict with call count and current rate.
    """
    global _call_count, _call_times

    with _rate_limiter_lock:
        stats = {
            "total_calls": _call_count,
            "calls_per_second": 0.0,
        }

        if len(_call_times) >= 2:
            time_span = _call_times[-1] - _call_times[0]
            if time_span > 0:
                stats["calls_per_second"] = (len(_call_times) - 1) / time_span

        return stats


def verify_patching():
    """
    Verify that RPC patching is actually working.
    Returns True if patching appears to be in place, False otherwise.
    """
    try:
        # Check if requests.Session.request has been patched (our fallback)
        import requests

        requests_patched = False
        if hasattr(requests.Session, "request"):
            # Check if it's been patched by looking for our function attributes
            # Our patched function will have different code than the original
            request_method = requests.Session.request
            # If it's been patched, it won't be the original bound method
            # We can check by seeing if it's a function (not a method descriptor)
            if callable(request_method):
                # Check if it references 'infura.io' in its code (our patch checks for this)
                import inspect

                try:
                    source = inspect.getsource(request_method)
                    if "infura.io" in source:
                        requests_patched = True
                except (OSError, TypeError):
                    # Can't get source, but that's okay - assume it might be patched
                    # For now, we'll check other methods
                    pass

        # Also check for boa-specific patches
        import boa

        # Try multiple ways to find the ForkDB instance (same as patch_rpc_client_after_fork)
        fork_db = None

        if hasattr(boa, "env") and hasattr(boa.env, "_fork_db"):
            fork_db = boa.env._fork_db

        if fork_db is None and hasattr(boa, "env") and hasattr(boa.env, "evm"):
            if hasattr(boa.env.evm, "state") and hasattr(
                boa.env.evm.state, "_account_db"
            ):
                account_db = boa.env.evm.state._account_db
                if hasattr(account_db, "_rpc"):
                    fork_db = account_db

        if fork_db is None and hasattr(boa, "env") and hasattr(boa.env, "evm"):
            if hasattr(boa.env.evm, "state") and hasattr(
                boa.env.evm.state, "account_db"
            ):
                account_db = boa.env.evm.state.account_db
                if hasattr(account_db, "_rpc"):
                    fork_db = account_db

        if (
            fork_db is not None
            and hasattr(fork_db, "_rpc")
            and hasattr(fork_db._rpc, "fetch")
        ):
            fetch_method = fork_db._rpc.fetch
            # Check if it's been wrapped (has __wrapped__ attribute from functools.wraps)
            if hasattr(fetch_method, "__wrapped__"):
                return True
            # Or check if it's a bound method that might be our wrapper
            if hasattr(fetch_method, "__func__"):
                func = fetch_method.__func__
                if hasattr(func, "__wrapped__"):
                    return True

        # If we patched requests, that's good enough
        # (The requests patch is our fallback and should always be active)
        return requests_patched
    except Exception:
        # If verification fails, assume patching might still work (requests fallback)
        # But return False to be safe
        return False
