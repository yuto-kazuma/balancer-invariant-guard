// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {FixedPoint} from "./FixedPoint.sol";

/// @title Simplified StableSwap math for Balancer rounding PoC
/// @dev Focuses on reproducing rounding asymmetry impact, not full Curve math
library StableMath {
    using FixedPoint for uint256;

    /// @notice Simplified invariant: sum of scaled balances
    function calculateInvariant(uint256[] memory balances, uint256) internal pure returns (uint256) {
        return balances[0] + balances[1];
    }

    /// @notice Exact-out swap: compute amountIn from amountOut
    /// @param roundOutDown Vulnerable path rounds output down before input calc
    function calcInGivenOut(
        uint256[] memory balances,
        uint256 tokenIndexIn,
        uint256 tokenIndexOut,
        uint256 amountOut,
        uint256,
        bool roundOutDown
    ) internal pure returns (uint256 amountIn) {
        if (balances[tokenIndexOut] < amountOut) return 0;

        uint256 balanceOut = balances[tokenIndexOut];
        uint256 balanceIn = balances[tokenIndexIn];
        if (balanceIn == 0 || balanceOut == 0 || amountOut == 0) return 0;

        // Constant-sum approximation: amountIn ~= amountOut * balanceIn / balanceOut
        amountIn = (amountOut * balanceIn) / balanceOut;
        if (amountIn == 0 && amountOut > 0) amountIn = 1;

        if (roundOutDown) {
            // Vulnerable: undercharge on exact-out at low wei boundaries
            // Models Balancer _upscale mulDown + StableMath compounding
            if (amountOut <= 100) {
                amountIn = amountIn.mulDown(FixedPoint.ONE - 5e15); // ~0.5% undercharge per swap
            } else {
                amountIn = amountIn.mulDown(FixedPoint.ONE - 1e14); // ~0.01% undercharge
            }
        }
    }

    /// @notice Compute effective D after simulating a swap (for invariant tracking)
    function invariantAfterSwap(
        uint256[] memory balances,
        uint256 tokenIndexOut,
        uint256 amountOut,
        uint256 amountIn,
        uint256 tokenIndexIn
    ) internal pure returns (uint256) {
        uint256[] memory newBalances = new uint256[](2);
        newBalances[0] = balances[0];
        newBalances[1] = balances[1];
        newBalances[tokenIndexOut] -= amountOut;
        newBalances[tokenIndexIn] += amountIn;
        return calculateInvariant(newBalances, 0);
    }
}
