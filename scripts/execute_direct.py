import os
import boa

# Setup Boa
infura_key = os.environ.get("INFURA_API_KEY")
etherscan_api_key = os.environ.get("ETHERSCAN_API_KEY")
rpc_url = f"https://mainnet.infura.io/v3/{infura_key}"
boa.fork(rpc_url)
boa.env.eoa = "0x57757E3D981446D585Af0D9Ae4d7DF6D64647806"  # WETH Whale

# Setup contracts
direct_path = "contracts/Direct.vy"
direct_deployer = boa.load_partial(direct_path)
direct_contract = direct_deployer.deploy()

mock_path = "contracts/mocks/MockToken.vy"
weth = boa.load_partial(mock_path).at("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")
usdc = boa.load_partial(mock_path).at("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")

# Confirm Swap
dx = 10**18
quote_value = direct_contract.quote_weth_usdc(dx)
print(f"Quoted: {quote_value}")


# Execute Swap
init_usdc = usdc.balanceOf(boa.env.eoa)
init_weth = weth.balanceOf(boa.env.eoa)

print(f"Init USDC: {init_usdc}")
print(f"Init WETH: {init_weth}")
weth.approve(direct_contract, dx)
direct_contract.swap_weth_usdc(dx, 0)

print(f"Final USDC: {usdc.balanceOf(boa.env.eoa)}")
print(f"Final WETH: {weth.balanceOf(boa.env.eoa)}")

assert usdc.balanceOf(boa.env.eoa) > init_usdc
print("Success")
