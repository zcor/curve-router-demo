"""
@title Router-NG Example WETH-USDC
"""

# Constants
router: constant(address) = 0x45312ea0eFf7E09C83CBE249fa1d7598c4C8cd4e
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


interface RouterNG:
    def get_dy(
        route: address[11], sp: uint256[5][5], amt: uint256, pools: address[5]
    ) -> uint256: view
    def exchange(
        route: address[11], sp: uint256[5][5], amt: uint256, min_dy: uint256
    ) -> uint256: nonpayable


# External Functions
@external
@view
def quote_weth_usdc_router(dx: uint256) -> uint256:
    r: address[11] = empty(address[11])
    sp: uint256[5][5] = empty(uint256[5][5])
    ps: address[5] = empty(address[5])
    (r, sp, ps) = self._route_params()
    return staticcall RouterNG(router).get_dy(r, sp, dx, ps)


@external
def swap_weth_usdc_router(dx: uint256, min_dy: uint256) -> uint256:
    # Intake Token
    extcall Token(WETH).approve(router, dx)
    extcall Token(WETH).transferFrom(msg.sender, self, dx)

    # Exchange
    r: address[11] = empty(address[11])
    sp: uint256[5][5] = empty(uint256[5][5])
    ps: address[5] = empty(address[5])
    (r, sp, ps) = self._route_params()

    retval: uint256 = extcall RouterNG(router).exchange(r, sp, dx, min_dy)

    # Return Token
    extcall Token(USDC).transfer(msg.sender, retval)
    return retval


# Internal Functions
@internal
@view
def _route_params() -> (address[11], uint256[5][5], address[5]):
    i: uint256 = self._get_index(WETH)
    j: uint256 = self._get_index(USDC)

    route: address[11] = empty(address[11])
    route[0] = WETH
    route[1] = pool
    route[2] = USDC

    pools: address[5] = empty(address[5])
    pools[0] = pool

    sp: uint256[5][5] = empty(uint256[5][5])

    # [i, j, swap_type=1 (direct), pool_type≈2 (2-coin crypto), n_coins=2]
    sp[0][0] = i
    sp[0][1] = j
    sp[0][2] = 1
    sp[0][3] = 3
    sp[0][4] = 3

    return route, sp, pools


@internal
@view
def _get_index(_addr: address) -> uint256:
    for _i: uint256 in range(3):
        if staticcall Pool(pool).coins(_i) == _addr:
            return _i
    raise ("Coin not found")
