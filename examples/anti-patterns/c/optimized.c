/* C 最適化版。RESULT 名と checksum は baseline.c と同一。
 * build: gcc -O3 -fopenmp optimized.c -o optimized
 *
 * 変更点（すべて整数演算なので結果は厳密一致）:
 *   axpy      : AoS -> SoA、init と update を融合（v は update 後どこからも読まれない）
 *   matmul    : i,j,k -> i,k,j（C は行優先。内側 j が連続になりベクトル化できる）
 *   sum2d     : 列方向走査 -> 行方向走査（連続アクセス）
 *   matmul_omp: 外側 i の並列はそのまま、内側を i,k,j に変更
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#ifdef _OPENMP
#include <omp.h>
#endif

#define N_PARTICLES 2000000
#define MAT_N 384
#define GRID 3000

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}

static int64_t axpy_soa(void) {
    const size_t n = N_PARTICLES;
    int64_t *x = malloc(n * sizeof *x);
    int64_t *y = malloc(n * sizeof *y);
    int64_t *z = malloc(n * sizeof *z);
    for (size_t i = 0; i < n; ++i) {
        x[i] = (int64_t)(i % 1000) + (int64_t)(i % 7) + 3;
        y[i] = (int64_t)(i % 997) + (int64_t)(i % 11) + 5;
        z[i] = (int64_t)(i % 991) + (int64_t)(i % 13) + 7;
    }
    int64_t sum = 0;
    for (size_t i = 0; i < n; ++i) sum += x[i] + y[i] + z[i];
    free(x);
    free(y);
    free(z);
    return sum;
}

static int64_t matmul_ikj(int n, int64_t *a, int64_t *b, int64_t *c) {
    for (int i = 0; i < n; ++i) {
        int64_t *ci = c + (size_t)i * n;
        const int64_t *ai = a + (size_t)i * n;
        for (int k = 0; k < n; ++k) {
            const int64_t aik = ai[k];
            const int64_t *bk = b + (size_t)k * n;
            for (int j = 0; j < n; ++j) ci[j] += aik * bk[j];
        }
    }
    int64_t sum = 0;
    for (int i = 0; i < n * n; ++i) sum += c[i];
    return sum;
}

static int64_t sum2d_row(int n, int64_t *a) {
    int64_t s0 = 0, s1 = 0, s2 = 0, s3 = 0; /* 4 本の加算鎖で依存を切る */
    const int len = n * n;
    int i = 0;
    for (; i + 4 <= len; i += 4) {
        s0 += a[i];
        s1 += a[i + 1];
        s2 += a[i + 2];
        s3 += a[i + 3];
    }
    for (; i < len; ++i) s0 += a[i];
    return (s0 + s1) + (s2 + s3);
}

static int64_t matmul_omp_ikj(int n, int64_t *a, int64_t *b, int64_t *c) {
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        int64_t *ci = c + (size_t)i * n;
        const int64_t *ai = a + (size_t)i * n;
        for (int k = 0; k < n; ++k) {
            const int64_t aik = ai[k];
            const int64_t *bk = b + (size_t)k * n;
            for (int j = 0; j < n; ++j) ci[j] += aik * bk[j];
        }
    }
    int64_t sum = 0;
    for (int i = 0; i < n * n; ++i) sum += c[i];
    return sum;
}

static int64_t *make_matrix(int n, int seed) {
    int64_t *m = calloc((size_t)n * n, sizeof(int64_t));
    for (int i = 0; i < n * n; ++i) m[i] = (i * 7 + seed) % 11;
    return m;
}

static void run(const char *name, double *median, int reps, int64_t (*fn)(void)) {
    double samples[16];
    int64_t checksum = 0;
    for (int r = 0; r < reps; ++r) {
        double t0 = now_ms();
        checksum = fn();
        samples[r] = now_ms() - t0;
    }
    for (int i = 1; i < reps; ++i)
        for (int j = i; j > 0 && samples[j - 1] > samples[j]; --j) {
            double tmp = samples[j];
            samples[j] = samples[j - 1];
            samples[j - 1] = tmp;
        }
    *median = samples[reps / 2];
    printf("RESULT %s %.3f %lld\n", name, *median, (long long)checksum);
}

static int64_t *g_a, *g_b, *g_c;
static int64_t *g_grid;

static int64_t once_matmul(void) {
    for (int i = 0; i < MAT_N * MAT_N; ++i) g_c[i] = 0;
    return matmul_ikj(MAT_N, g_a, g_b, g_c);
}

static int64_t once_sum2d(void) { return sum2d_row(GRID, g_grid); }

static int64_t once_matmul_omp(void) {
    for (int i = 0; i < MAT_N * MAT_N; ++i) g_c[i] = 0;
    return matmul_omp_ikj(MAT_N, g_a, g_b, g_c);
}

int main(void) {
    g_a = make_matrix(MAT_N, 1);
    g_b = make_matrix(MAT_N, 2);
    g_c = calloc((size_t)MAT_N * MAT_N, sizeof(int64_t));
    g_grid = make_matrix(GRID, 3);
    double med;

    run("axpy", &med, 3, axpy_soa);
    run("matmul", &med, 3, once_matmul);
    run("sum2d", &med, 3, once_sum2d);
    run("matmul_omp", &med, 3, once_matmul_omp);
    return 0;
}
