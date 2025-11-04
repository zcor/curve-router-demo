"""
@title Direct Swap Example WETH-USDC
"""

# Constants
pool: constant(address) = 0x7F86Bf177Dd4F3494b841a37e810A34dD56c829B
WETH: constant(address) = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
USDC: constant(address) = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48

# Interfaces
interface Pool:
    def coins(i: uint256) -> address: view
    def get_dy(i: uint256, j: uint256, dx: uint256) -> uint256: view
    def exchange(
        i: uint256, j: uint256, dx: uint256, min_dy: uint256
    ) -> uint256: nonpayable


interface Token:
    def approve(_addr: address, _val: uint256): nonpayable
    def transferFrom(_from: address, _to: address, _val: uint256): nonpayable
    def transfer(_to: address, _val: uint256): nonpayable


# External Functions
@external
@view
def quote_weth_usdc(dx: uint256) -> uint256:
    i: uint256 = self._get_index(WETH)
    j: uint256 = self._get_index(USDC)
    return staticcall Pool(pool).get_dy(i, j, dx)


@external
def swap_weth_usdc(dx: uint256, min_dy: uint256) -> uint256:
    i: uint256 = self._get_index(WETH)
    j: uint256 = self._get_index(USDC)

    # Intake Token
    extcall Token(WETH).approve(pool, dx)
    extcall Token(WETH).transferFrom(msg.sender, self, dx)

    # Exchange
    retval: uint256 = extcall Pool(pool).exchange(i, j, dx, min_dy)

    # Return Token
    extcall Token(USDC).transfer(msg.sender, retval)
    return retval


# Internal Functions
@internal
@view
def _get_index(_addr: address) -> uint256:
    for _i: uint256 in range(3):
        if staticcall Pool(pool).coins(_i) == _addr:
            return _i
    raise ("Coin not found")
