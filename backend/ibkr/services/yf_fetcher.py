"""Download OHLCV data via yfinance batch download."""

import os
import tempfile
import time
import pandas as pd
import yfinance as yf

# Isolate yfinance's SQLite timezone cache per process to prevent concurrent-access errors
_tz_cache = os.path.join(tempfile.gettempdir(), f"yfinance_tz_{os.getpid()}")
try:
    yf.set_tz_cache_location(_tz_cache)
except Exception:
    pass


def _download_single(ticker: str, period: str) -> pd.DataFrame | None:
    """Download one ticker; returns DataFrame or None."""
    try:
        df = yf.download(
            tickers=ticker,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if not df.empty and len(df) >= 60:
            return df.dropna(how="all")
    except Exception:
        pass
    return None


def download_all(tickers: list[str], period: str = "1y", batch_size: int = 100) -> dict[str, pd.DataFrame]:
    """Batch-download OHLCV data. Returns {ticker: DataFrame}."""
    results: dict[str, pd.DataFrame] = {}
    need_retry: list[str] = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        try:
            raw = yf.download(
                tickers=batch,
                period=period,
                auto_adjust=True,
                progress=False,
                threads=True,
            )

            if len(batch) == 1:
                ticker = batch[0]
                if not raw.empty and len(raw) >= 60:
                    results[ticker] = raw.dropna(how="all")
                else:
                    need_retry.append(ticker)
            else:
                # MultiIndex columns: (field, ticker)
                for ticker in batch:
                    try:
                        df = raw.xs(ticker, level=1, axis=1).dropna(how="all")
                        if len(df) >= 60:
                            results[ticker] = df
                        else:
                            need_retry.append(ticker)
                    except (KeyError, Exception):
                        need_retry.append(ticker)

        except Exception as e:
            print(f"  [warn] batch {i // batch_size + 1} failed: {e}")
            need_retry.extend(batch)

        if i + batch_size < len(tickers):
            time.sleep(0.25)

    # Retry batch failures individually — avoids false "possibly delisted" for valid symbols
    if need_retry:
        print(f"  Retrying {len(need_retry)} symbols individually…")
        for ticker in need_retry:
            df = _download_single(ticker, period)
            if df is not None:
                results[ticker] = df
            time.sleep(0.1)

    return results
