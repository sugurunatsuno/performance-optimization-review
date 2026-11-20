"use strict";

// baseline.ts の最適化版。checksum は baseline と厳密一致。
// すべて整数演算なので、走査順・格納形式の変更で値は変わらない。
declare const performance: { now(): number };
declare const process: { stdout: { write(s: string): void } };
export {};
const N = 320;
const GRID = 3000;
const NP = 2_000_000;
const ALLOC_OUTER = 50_000;
const ALLOC_INNER = 64;

const a = new Int32Array(N * N);
const b = new Int32Array(N * N);
for (let i = 0; i < N * N; i++) {
  a[i] = (i * 7 + 1) % 11;
  b[i] = (i * 7 + 2) % 11;
}
const c = new Int32Array(N * N);

const grid = new Int32Array(GRID * GRID);
for (let i = 0; i < grid.length; i++) grid[i] = (i * 7 + 3) % 101;

function matmul(): number {
  // i,k,j: 内側 j が連続アクセスになり、c の行をまとめて更新できる
  c.fill(0);
  for (let i = 0; i < N; i++) {
    const ci = i * N;
    for (let k = 0; k < N; k++) {
      const aik = a[ci + k];
      const bk = k * N;
      for (let j = 0; j < N; j++) c[ci + j] += aik * b[bk + j];
    }
  }
  let sum = 0;
  for (let i = 0; i < c.length; i++) sum += c[i];
  return sum;
}

function sum2d(): number {
  // 行優先（フラット配列をそのまま順に走査）
  let sum = 0;
  for (let i = 0; i < grid.length; i++) sum += grid[i];
  return sum;
}

function aos(): number {
  // AoS -> SoA。フィールドごとの Int32Array に分ける
  const x = new Int32Array(NP);
  const y = new Int32Array(NP);
  const z = new Int32Array(NP);
  const vx = new Int32Array(NP);
  const vy = new Int32Array(NP);
  const vz = new Int32Array(NP);
  for (let i = 0; i < NP; i++) {
    x[i] = i % 1000;
    y[i] = i % 997;
    z[i] = i % 991;
    vx[i] = i % 7;
    vy[i] = i % 11;
    vz[i] = i % 13;
  }
  for (let i = 0; i < NP; i++) {
    x[i] += vx[i] + 3;
    y[i] += vy[i] + 5;
    z[i] += vz[i] + 7;
  }
  let sum = 0;
  for (let i = 0; i < NP; i++) sum += x[i] + y[i] + z[i];
  return sum;
}

const allocBuf = new Int32Array(ALLOC_INNER);

function alloc(): number {
  // バッファを 1 回だけ確保して再利用（書き込みと読み出しは baseline と同じ）
  let sum = 0;
  for (let i = 0; i < ALLOC_OUTER; i++) {
    for (let j = 0; j < ALLOC_INNER; j++) allocBuf[j] = (i + j) % 97;
    for (let j = 0; j < ALLOC_INNER; j++) sum += allocBuf[j];
  }
  return sum;
}

function median(xs: number[]): number {
  return xs.slice().sort((x, y) => x - y)[xs.length >> 1];
}

function bench(fn: () => number): [number, number] {
  let checksum = 0;
  for (let r = 0; r < 2; r++) checksum = fn(); // JIT ウォームアップ
  const samples: number[] = [];
  for (let r = 0; r < 5; r++) {
    const t0 = performance.now();
    checksum = fn();
    samples.push(performance.now() - t0);
  }
  return [median(samples), checksum];
}

const cases: Array<[string, () => number]> = [
  ["matmul", matmul],
  ["sum2d", sum2d],
  ["aos", aos],
  ["alloc", alloc],
];

for (const [name, fn] of cases) {
  const [ms, checksum] = bench(fn);
  process.stdout.write(`RESULT ${name} ${ms.toFixed(3)} ${checksum}\n`);
}
