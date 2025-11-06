import os
import boa

# Setup Boa
infura_key = os.environ.get("INFURA_API_KEY")
etherscan_api_key = os.environ.get("ETHERSCAN_API_KEY")
rpc_url = f"https://mainnet.infura.io/v3/{infura_key}"
boa.fork(rpc_url)
boa.env.eoa = "0x835678a611B28684005a5e2233695fB6cbbB0007"  # USDT Whale

# Setup contracts
direct_path = "contracts/Spark.vy"
direct_deployer = boa.load_partial(direct_path)
direct_contract = direct_deployer.deploy()

mock_path = "contracts/mocks/MockToken.vy"
usdt = boa.load_partial(mock_path).at("0xdAC17F958D2ee523a2206206994597C13D831ec7")
susds = boa.load_partial(mock_path).at("0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD")

# Confirm Swap
dx = 100 * 10**6 # 100 USDT (6 Decimals)
quote_value = direct_contract.quote_usdt_susds(dx)
print(f"Quoted: {quote_value}")


