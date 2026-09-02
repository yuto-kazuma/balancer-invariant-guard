// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Test} from "forge-std/Test.sol";
import {VulnerableStablePool} from "../src/VulnerableStablePool.sol";
import {MockERC20} from "../src/MockERC20.sol";

/// @title Invariant tests that InvariantBreaker auto-generates for CI
contract InvariantTest is Test {
    VulnerableStablePool pool;
    MockERC20 token0;
    MockERC20 token1;

    address user = makeAddr("user");

    function setUp() public {
        token0 = new MockERC20("cbETH", "cbETH", 18);
        token1 = new MockERC20("wstETH", "wstETH", 18);
        pool = new VulnerableStablePool(address(token0), address(token1));

        token0.mint(user, 100_000e18);
        token1.mint(user, 100_000e18);
        vm.startPrank(user);
        token0.approve(address(pool), type(uint256).max);
        token1.approve(address(pool), type(uint256).max);
        pool.joinPool(50_000e18, 50_000e18, user);
        vm.stopPrank();
    }

    function test_invariant_D_positiveWithLiquidity() public view {
        uint256[] memory balances = pool.getBalances();
        if (balances[0] + balances[1] > 0) {
            assertGt(pool.calculateInvariant(), 0, "D must be positive when pool has liquidity");
        }
    }

    function test_invariant_bptRateIsPositive() public view {
        assertGt(pool.getRate(), 0, "BPT rate must be positive");
    }
}
