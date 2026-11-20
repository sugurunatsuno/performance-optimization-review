// Rust の典型的なアンチパターンを修正した版。
// build: rustc -O optimized.rs -o optimized

use std::time::Instant;

const MAT_N: usize = 384;
const PART_N: usize = 2_000_000;
const GRID_N: usize = 3_000;
const ALLOC_OUTER: usize = 200_000;
const ALLOC_INNER: usize = 64;
const REPEATS: usize = 3;

#[derive(Clone, Copy)]
struct Particle {
    x: i64,
    y: i64,
    z: i64,
    vx: i64,
    vy: i64,
    vz: i64,
}

fn make_matrix(n: usize, seed: i64) -> Vec<i64> {
    (0..n * n)
        .map(|i| (i as i64 * 7 + seed) % 11)
        .collect()
}

// i-k-j: 内側 j が b / c の連続領域を走査する。c の各要素は k 昇順に加算するので
// 整数の総和は元の i-j-k と同一 (integer wrap のみ、順序も同じ)。
fn matmul_ikj(a: &[i64], b: &[i64], c: &mut [i64], n: usize) {
    for i in 0..n {
        let arow = &a[i * n..i * n + n];
        let crow = &mut c[i * n..i * n + n];
        for (k, &aik) in arow.iter().enumerate() {
            let brow = &b[k * n..k * n + n];
            for (cij, &bkj) in crow.iter_mut().zip(brow) {
                *cij += aik * bkj;
            }
        }
    }
}

// 更新と総和を 1 パスに融合。加算順は元と同じ (i 昇順)。
fn aos_update() -> i64 {
    let mut particles: Vec<Particle> = (0..PART_N)
        .map(|i| Particle {
            x: (i % 1000) as i64,
            y: (i % 997) as i64,
            z: (i % 991) as i64,
            vx: (i % 7) as i64,
            vy: (i % 11) as i64,
            vz: (i % 13) as i64,
        })
        .collect();
    let mut total = 0;
    for p in particles.iter_mut() {
        p.x += p.vx + 3;
        p.y += p.vy + 5;
        p.z += p.vz + 7;
        total += p.x + p.y + p.z;
    }
    total
}

// row-major バッファなので行を外側、連続する列を内側にする。
fn sum2d_row(a: &[i64], n: usize) -> i64 {
    let mut total = 0;
    for i in 0..n {
        for j in 0..n {
            total += a[i * n + j];
        }
    }
    total
}

// 固定長バッファをスタックに 1 個だけ置き、ループ内の確保をなくす。
// Vec をループ外で再利用する案 (clear + push) より実測が速かった。
fn alloc_in_loop() -> i64 {
    let mut total = 0;
    let mut buffer = [0i64; ALLOC_INNER];
    for i in 0..ALLOC_OUTER {
        for j in 0..ALLOC_INNER {
            buffer[j] = ((i + j) % 97) as i64;
        }
        total += buffer.iter().sum::<i64>();
    }
    total
}

fn median_ms(mut samples: Vec<f64>) -> f64 {
    samples.sort_by(|a, b| a.partial_cmp(b).unwrap());
    samples[samples.len() / 2]
}

fn bench<F: FnMut() -> i64>(name: &str, mut f: F) {
    let mut samples = Vec::with_capacity(REPEATS);
    let mut checksum = 0;
    for _ in 0..REPEATS {
        let start = Instant::now();
        checksum = f();
        samples.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    println!("RESULT {} {:.6} {}", name, median_ms(samples), checksum);
}

fn main() {
    let a = make_matrix(MAT_N, 1);
    let b = make_matrix(MAT_N, 2);
    let mut c = vec![0i64; MAT_N * MAT_N];
    let grid = make_matrix(GRID_N, 3);

    bench("matmul", || {
        c.iter_mut().for_each(|v| *v = 0);
        matmul_ikj(&a, &b, &mut c, MAT_N);
        c.iter().sum()
    });
    bench("axpy", aos_update);
    bench("sum2d", || sum2d_row(&grid, GRID_N));
    bench("alloc", alloc_in_loop);
}
