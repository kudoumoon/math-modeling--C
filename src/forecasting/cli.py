from __future__ import annotations

import argparse
import json

from .backtest import run_backtest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run leakage-safe Q3/Q4 forecasting backtest")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/forecast.json")
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()
    result = run_backtest(args.root, args.config, output_root=args.output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
