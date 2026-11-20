"use strict";

// 典型的なアンチパターン（変更禁止）。仕様は ../SPEC.md。
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

function matmul() {
  // i,j,k のまま: 内側 k で b を列方向に読む
  c.fill(0);
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      for (let k = 0; k < N; k++) {
        c[i * N + j] += a[i * N + k] * b[k * N + j];
      }
    }
  }
  let sum = 0;
  for (let i = 0; i < c.length; i++) sum += c[i];
  return sum;
}

function sum2d() {
  // 列優先: 内側 i で grid を飛び飛びに読む
  let sum = 0;
  for (let j = 0; j < GRID; j++) {
    for (let i = 0; i < GRID; i++) sum += grid[i * GRID + j];
  }
  return sum;
}

function aos() {
  const p = new Array(NP);
  for (let i = 0; i < NP; i++) {
    p[i] = {
      x: i % 1000,
      y: i % 997,
      z: i % 991,
      vx: i % 7,
      vy: i % 11,
      vz: i % 13,
    };
  }
  for (let i = 0; i < NP; i++) {
    const o = p[i];
    o.x += o.vx + 3;
    o.y += o.vy + 5;
    o.z += o.vz + 7;
  }
  let sum = 0;
  for (let i = 0; i < NP; i++) {
    const o = p[i];
    sum += o.x + o.y + o.z;
  }
  return sum;
}

function alloc() {
  // 外側ループごとに新しい配列を確保
  let sum = 0;
  for (let i = 0; i < ALLOC_OUTER; i++) {
    const buf = new Array(ALLOC_INNER);
    for (let j = 0; j < ALLOC_INNER; j++) buf[j] = (i + j) % 97;
    for (let j = 0; j < ALLOC_INNER; j++) sum += buf[j];
  }
  return sum;
}

function median(xs) {
  return xs.slice().sort((x, y) => x - y)[xs.length >> 1];
}

function bench(fn) {
  let checksum = 0;
  for (let r = 0; r < 2; r++) checksum = fn(); // JIT ウォームアップ
  const samples = [];
  for (let r = 0; r < 5; r++) {
    const t0 = process.hrtime.bigint();
    checksum = fn();
    samples.push(Number(process.hrtime.bigint() - t0) / 1e6);
  }
  return [median(samples), checksum];
}

for (const [name, fn] of [
  ["matmul", matmul],
  ["sum2d", sum2d],
  ["aos", aos],
  ["alloc", alloc],
]) {
  const [ms, checksum] = bench(fn);
  console.log(`RESULT ${name} ${ms.toFixed(3)} ${checksum}`);
}
