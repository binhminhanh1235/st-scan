"""
Test Walk-Forward & Ablation (Definition of Done #1 & #2):
1. Walk-forward purged K-fold với embargo 5 phiên.
2. Ablation test: delta EV >= +0.1R hoặc win-rate +5%, retention >= 40%, Flow thắng baseline.
"""

import pytest
from wfe.backtest.walk_forward import WalkForwardValidator, run_ablation_test


def test_walk_forward_purged_k_fold_embargo():
    """Verify purged K-fold generates training and test windows separated by 5-bar embargo."""
    total_bars = 500
    validator = WalkForwardValidator(k_folds=5, embargo_bars=5)
    splits = validator.split(total_bars)

    assert len(splits) == 4
    for (train_start, train_end), (test_start, test_end) in splits:
        # Check embargo gap
        assert test_start == train_end + 5
        assert test_start < test_end
        assert train_start == 0


def test_ablation_engine_delta_and_retention():
    """Verify ablation test logic and thresholds."""
    # Full system trades: high EV, win rate 60%
    full_trades = [
        {"r_return": 1.5}, {"r_return": -1.0}, {"r_return": 2.0},
        {"r_return": 0.8}, {"r_return": -1.0}, {"r_return": 1.2}
    ]
    # Ablated trades (without Flow engine): lower EV, win rate 45%
    ablated_trades = [
        {"r_return": 0.5}, {"r_return": -1.0}, {"r_return": -1.0},
        {"r_return": 1.0}, {"r_return": -1.0}, {"r_return": 0.2},
        {"r_return": -1.0}, {"r_return": 0.8}
    ]

    result = run_ablation_test(full_trades, ablated_trades)
    assert result.delta_ev >= 0.10
    assert result.delta_win_rate >= 5.0
    assert result.retention_pct >= 40.0
    assert result.is_passed is True
