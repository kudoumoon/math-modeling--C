from __future__ import annotations

import argparse
import json

from .backtest import run_backtest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run leakage-safe Q3/Q4 forecasting backtest")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/forecast.json")
    args = parser.parse_args()
    result = run_backtest(args.root, args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

