"""
Boa setup utility - handles RPC patching and environment setup.
This keeps the execution scripts clean and focused on educational content.
"""

import os
import time

from rpc_retry import patch_rpc_client, patch_rpc_client_after_fork, verify_patching


def setup_boa_environment(rpc_url: str = None, verify: bool = True) -> None:
    """
    Set up boa environment with RPC patching and rate limiting.

    Args:
        rpc_url: Optional RPC URL. If not provided, constructs from INFURA_API_KEY env var.
        verify: Whether to verify patching worked (default: True)

    Usage:
        from boa_setup import setup_boa_environment
        setup_boa_environment()
        boa.fork(rpc_url)
    """
    import boa

    # Patch RPC client with retry logic before forking
    patch_rpc_client()

    # If no RPC URL provided, construct from environment
    if rpc_url is None:
        infura_key = os.environ.get("INFURA_API_KEY")
        if not infura_key:
            raise ValueError("INFURA_API_KEY environment variable not set")
        rpc_url = f"https://mainnet.infura.io/v3/{infura_key}"

    # Fork the blockchain
    boa.fork(rpc_url)

    # Also patch after fork as backup (in case pre-fork patching didn't work)
    patch_rpc_client_after_fork()

    # Delay after fork to let initial RPC calls settle
    # ForkDB makes many RPC calls during setup, so we need to wait
    time.sleep(1.0)

    # Verify patching worked
    if verify:
        if not verify_patching():
            print(
                "⚠️  WARNING: RPC patching verification failed! Calls may not be throttled."
            )
        else:
            print("✓ RPC patching verified - rate limiting is active")

    return rpc_url
