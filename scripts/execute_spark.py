import time

import boa
from boa_setup import setup_boa_environment

# Setup Boa environment (handles RPC patching, rate limiting, etc.)
setup_boa_environment()

# Set the EOA (Externally Owned Account) to use for transactions
boa.env.eoa = "0x859C9980931fa0A63765fD8EF2e29918Af5b038C"  # sUSDS Whale
# Setup contracts
direct_path = "contracts/Spark.vy"
direct_deployer = boa.load_partial(direct_path)
direct_contract = direct_deployer.deploy()

mock_path = "contracts/mocks/MockToken.vy"
usdt = boa.load_partial(mock_path).at("0xdAC17F958D2ee523a2206206994597C13D831ec7")
susds = boa.load_partial(mock_path).at("0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD")

# Test reverse swap: sUSDS -> USDT
# sUSDS has 18 decimals, so 100 sUSDS = 100 * 10**18
dx = 100 * 10**18  # 100 sUSDS (18 decimals)
quote_value = direct_contract.quote_susds_usdt(dx)
print(f"Quoted: {quote_value}")

# Small delay to let RPC calls from quote operation settle
time.sleep(0.5)

# Execute Swap
init_usdt = usdt.balanceOf(boa.env.eoa)
init_susds = susds.balanceOf(boa.env.eoa)

print(f"Init USDT: {init_usdt}")
print(f"Init sUSDS: {init_susds}")
susds.approve(direct_contract, dx)
direct_contract.swap_susds_usdt(dx, 0)

print(f"Final USDT: {usdt.balanceOf(boa.env.eoa)}")
print(f"Final sUSDS: {susds.balanceOf(boa.env.eoa)}")

assert usdt.balanceOf(boa.env.eoa) > init_usdt
print("Success")
