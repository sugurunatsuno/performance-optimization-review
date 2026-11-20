"""baseline.py の最適化版。CASES と戻り値の契約は baseline と同じ。"""

from __future__ import annotations

import numpy as np

N_AXPY = 1_000_000
M_ROWS, M_COLS = 1_500, 1_500
N_TANH = 300_000
COPY_ROWS, COPY_COLS = 4_000, 4_000

a = np.arange(N_AXPY, dtype=np.int64)
b = np.arange(N_AXPY, dtype=np.int64) % 97
out = np.empty_like(a)

m = np.arange(M_ROWS * M_COLS, dtype=np.int64).reshape(M_ROWS, M_COLS) % 1_011
m_copy = np.arange(COPY_ROWS * COPY_COLS, dtype=np.int64).reshape(
    COPY_ROWS, COPY_COLS
) % 251
t = np.linspace(-3.0, 3.0, N_TANH)


def axpy() -> np.ndarray:
    # 要素ごとの独立した整数加算: Python ループを ufunc に置換し、同じ out を更新
    np.add(a, b, out=out)
    return out[::1000].copy()


def colsum() -> np.ndarray:
    # 整数の総和は結合則が厳密に成り立つため、reduction への置換は exact
    return m.sum(axis=0)


def tanh_vec() -> np.ndarray:
    return np.tanh(t)


def colsum_copy() -> np.ndarray:
    # 列ごとの ascontiguousarray コピーをやめ、1 回の reduction に統合
    return m_copy.sum(axis=0)


CASES = {
    "axpy": (axpy, (), 5),
    "colsum": (colsum, (), 3),
    "tanh_vec": (tanh_vec, (), 3),
    "colsum_copy": (colsum_copy, (), 3),
}
