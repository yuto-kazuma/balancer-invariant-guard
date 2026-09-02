// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title Minimal FixedPoint math mirroring Balancer V2 patterns
/// @notice Demonstrates the rounding asymmetry that caused the Nov 2025 exploit
library FixedPoint {
    uint256 internal constant ONE = 1e18;

    function mulDown(uint256 a, uint256 b) internal pure returns (uint256) {
        return (a * b) / ONE;
    }

    function mulUp(uint256 a, uint256 b) internal pure returns (uint256) {
        uint256 product = a * b;
        if (product == 0) return 0;
        return ((product - 1) / ONE) + 1;
    }

    function divDown(uint256 a, uint256 b) internal pure returns (uint256) {
        if (a == 0) return 0;
        return (a * ONE) / b;
    }

    function divUp(uint256 a, uint256 b) internal pure returns (uint256) {
        if (a == 0) return 0;
        return ((a * ONE - 1) / b) + 1;
    }
}
