"""NumPy の典型的なアンチパターン（変更禁止）。"""

from __future__ import annotations

import math

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
    for i in range(N_AXPY):
        out[i] = a[i] + b[i]
    return out[::1000].copy()


def colsum() -> np.ndarray:
    total = np.zeros(M_COLS, dtype=np.int64)
    for j in range(M_COLS):
        for i in range(M_ROWS):
            total[j] += m[i, j]
    return total


def tanh_vec() -> np.ndarray:
    return np.vectorize(math.tanh)(t)


def colsum_copy() -> np.ndarray:
    total = np.empty(COPY_COLS, dtype=np.int64)
    for j in range(COPY_COLS):
        column = np.ascontiguousarray(m_copy[:, j])
        total[j] = column.sum()
    return total


CASES = {
    "axpy": (axpy, (), 5),
    "colsum": (colsum, (), 3),
    "tanh_vec": (tanh_vec, (), 3),
    "colsum_copy": (colsum_copy, (), 3),
}
