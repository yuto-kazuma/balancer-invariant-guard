// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {FixedPoint} from "./FixedPoint.sol";
import {StableMath} from "./StableMath.sol";
import {MockERC20} from "./MockERC20.sol";

/// @title Minimal Composable Stable Pool reproducing Balancer V2 rounding bug
/// @notice Models the Nov 2025 exploit mechanism:
///   1. _upscale uses mulDown on GIVEN_OUT path
///   2. Rate provider introduces non-unitary scaling
///   3. Batch swaps at low liquidity compound precision loss
contract VulnerableStablePool {
    using FixedPoint for uint256;

    MockERC20 public immutable token0;
    MockERC20 public immutable token1;

    uint256 public totalSupply;
    uint256 public rate0 = 1114 * 1e15; // 1.114e18 - non-unitary rate (cbETH-style)
    uint256 public rate1 = 1e18;

    uint256 public trackedInvariant;

    mapping(address => uint256) public bptBalance;

    event Swap(address indexed user, uint256 amountIn, uint256 amountOut, bool givenOut);

    constructor(address _token0, address _token1) {
        token0 = MockERC20(_token0);
        token1 = MockERC20(_token1);
    }

    function getBalances() public view returns (uint256[] memory balances) {
        balances = new uint256[](2);
        balances[0] = token0.balanceOf(address(this));
        balances[1] = token1.balanceOf(address(this));
    }

    /// @notice Pool rate = invariant / totalSupply (BPT price proxy)
    function getRate() public view returns (uint256) {
        if (totalSupply == 0) return FixedPoint.ONE;
        uint256 d = StableMath.calculateInvariant(getBalances(), totalSupply);
        return (d * FixedPoint.ONE) / totalSupply;
    }

    function calculateInvariant() public view returns (uint256) {
        return StableMath.calculateInvariant(getBalances(), totalSupply);
    }

    function joinPool(uint256 amount0, uint256 amount1, address to) external {
        token0.transferFrom(msg.sender, address(this), amount0);
        token1.transferFrom(msg.sender, address(this), amount1);
        uint256 bptOut = (amount0 + amount1) / 2;
        if (bptOut == 0) bptOut = 1;
        totalSupply += bptOut;
        bptBalance[to] += bptOut;
        trackedInvariant = calculateInvariant();
    }

    /// @notice Vulnerable upscale - always mulDown (Balancer bug pattern)
    function _upscale(uint256 amount, uint256 rate) internal pure returns (uint256) {
        return amount.mulDown(rate);
    }

    /// @notice Single swap exact-out (GIVEN_OUT) - vulnerable path
    function swapGivenOut(uint256 tokenIn, uint256 tokenOut, uint256 amountOut) external returns (uint256 amountIn) {
        MockERC20 tIn = tokenIn == 0 ? token0 : token1;
        MockERC20 tOut = tokenOut == 0 ? token0 : token1;
        uint256 rate = tokenOut == 0 ? rate0 : rate1;

        uint256 scaledOut = _upscale(amountOut, rate);

        uint256[] memory balances = getBalances();
        amountIn = StableMath.calcInGivenOut(balances, tokenIn, tokenOut, scaledOut, totalSupply, true);
        require(amountIn > 0 && amountOut <= balances[tokenOut], "Insufficient liquidity");

        tIn.transferFrom(msg.sender, address(this), amountIn);
        tOut.transfer(msg.sender, amountOut);

        trackedInvariant = StableMath.invariantAfterSwap(balances, tokenOut, amountOut, amountIn, tokenIn);

        emit Swap(msg.sender, amountIn, amountOut, true);
    }

    struct BatchStep {
        uint256 tokenIn;
        uint256 tokenOut;
        uint256 amountOut;
    }

    /// @notice Batch swap - attacker compounds rounding errors (Balancer used 65+ steps)
    function batchSwapGivenOut(BatchStep[] calldata steps) external returns (uint256 totalPaidIn) {
        for (uint256 i = 0; i < steps.length; i++) {
            BatchStep calldata s = steps[i];
            MockERC20 tIn = s.tokenIn == 0 ? token0 : token1;
            MockERC20 tOut = s.tokenOut == 0 ? token0 : token1;
            uint256 rate = s.tokenOut == 0 ? rate0 : rate1;

            uint256 scaledOut = _upscale(s.amountOut, rate);
            uint256[] memory balances = getBalances();
            uint256 amountIn =
                StableMath.calcInGivenOut(balances, s.tokenIn, s.tokenOut, scaledOut, totalSupply, true);
            if (amountIn == 0 || s.amountOut > balances[s.tokenOut]) continue;

            tIn.transferFrom(msg.sender, address(this), amountIn);
            tOut.transfer(msg.sender, s.amountOut);
            totalPaidIn += amountIn;

            trackedInvariant =
                StableMath.invariantAfterSwap(balances, s.tokenOut, s.amountOut, amountIn, s.tokenIn);
        }
    }

    /// @notice Force low liquidity - exitSwap pattern from Balancer exploit
    function exitSwapDrain(uint256 amountOut0, uint256 amountOut1) external {
        token0.transfer(msg.sender, amountOut0);
        token1.transfer(msg.sender, amountOut1);
        trackedInvariant = calculateInvariant();
    }

    /// @notice Fixed swap path - upscale rounds UP (protocol-favoring mitigation)
    function swapGivenOutFixed(uint256 tokenIn, uint256 tokenOut, uint256 amountOut)
        external
        returns (uint256 amountIn)
    {
        MockERC20 tIn = tokenIn == 0 ? token0 : token1;
        MockERC20 tOut = tokenOut == 0 ? token0 : token1;
        uint256 rate = tokenOut == 0 ? rate0 : rate1;

        uint256 scaledOut = amountOut.mulUp(rate);

        uint256[] memory balances = getBalances();
        amountIn = StableMath.calcInGivenOut(balances, tokenIn, tokenOut, scaledOut, totalSupply, false);
        require(amountIn > 0 && amountOut <= balances[tokenOut], "Insufficient liquidity");

        tIn.transferFrom(msg.sender, address(this), amountIn);
        tOut.transfer(msg.sender, amountOut);

        trackedInvariant = StableMath.invariantAfterSwap(balances, tokenOut, amountOut, amountIn, tokenIn);
    }

    /// @notice Fair amountIn without vulnerability (for comparison)
    function fairAmountIn(uint256 tokenIn, uint256 tokenOut, uint256 amountOut) external view returns (uint256) {
        uint256 rate = tokenOut == 0 ? rate0 : rate1;
        uint256 scaledOut = amountOut.mulUp(rate);
        return StableMath.calcInGivenOut(getBalances(), tokenIn, tokenOut, scaledOut, totalSupply, false);
    }
}
