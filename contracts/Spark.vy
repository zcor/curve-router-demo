"""
@title Direct Swap Example USDT-SUSDS
"""

# Constants
pool: constant(address) = 0x00836Fe54625BE242BcFA286207795405ca4fD10
USDT: constant(address) = 0xdAC17F958D2ee523a2206206994597C13D831ec7 
SUSDS: constant(address) = 0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD

# Interfaces
interface Pool:
    def coins(i: uint256) -> address: view
    def get_dy(i: int128, j: int128, dx: uint256) -> uint256: view
    def exchange(
        i: int128, j: int128, dx: uint256, min_dy: uint256
    ) -> uint256: nonpayable


interface Token:
    def approve(_addr: address, _val: uint256): nonpayable
    def transferFrom(_from: address, _to: address, _val: uint256): nonpayable
    def transfer(_to: address, _val: uint256): nonpayable


# External Functions
@external
@view
def quote_usdt_susds(dx: uint256) -> uint256:
    i: int128 = self._get_index(USDT)
    j: int128 = self._get_index(SUSDS)
    return staticcall Pool(pool).get_dy(i, j, dx)


@external
def swap_usdt_susds(dx: uint256, min_dy: uint256) -> uint256:
    i: int128 = self._get_index(USDT)
    j: int128 = self._get_index(SUSDS)

    # Intake Token
    extcall Token(USDT).approve(pool, dx)
    extcall Token(USDT).transferFrom(msg.sender, self, dx)

    # Exchange
    retval: uint256 = extcall Pool(pool).exchange(i, j, dx, min_dy)

    # Return Token
    extcall Token(SUSDS).transfer(msg.sender, retval)
    return retval


# Internal Functions
@internal
@view
def _get_index(_addr: address) -> int128:
    for _i: uint256 in range(3):
        if staticcall Pool(pool).coins(_i) == _addr:
            return convert(_i, int128)
    raise ("Coin not found")
