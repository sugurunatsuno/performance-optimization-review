/* 独立検証用: 手法を 1 つずつ分離して比較する。
 * build: gcc -O3 -fopenmp independent.c -o independent
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define N_PARTICLES 2000000
#define MAT_N 384
#define GRID 3000

typedef struct {
    int64_t x, y, z;
    int64_t vx, vy, vz;
} Particle;

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}

static int64_t axpy_aos(void) {
    Particle *p = malloc(sizeof(Particle) * N_PARTICLES);
    for (int i = 0; i < N_PARTICLES; ++i) {
        p[i].x = i % 1000; p[i].y = i % 997; p[i].z = i % 991;
        p[i].vx = i % 7; p[i].vy = i % 11; p[i].vz = i % 13;
    }
    for (int i = 0; i < N_PARTICLES; ++i) {
        p[i].x += p[i].vx + 3;
        p[i].y += p[i].vy + 5;
        p[i].z += p[i].vz + 7;
    }
    int64_t sum = 0;
    for (int i = 0; i < N_PARTICLES; ++i) sum += p[i].x + p[i].y + p[i].z;
    free(p);
    return sum;
}

static int64_t axpy_aos_fused(void) {
    Particle *p = malloc(sizeof(Particle) * N_PARTICLES);
    for (int i = 0; i < N_PARTICLES; ++i) {
        p[i].x = i % 1000; p[i].y = i % 997; p[i].z = i % 991;
        p[i].vx = i % 7; p[i].vy = i % 11; p[i].vz = i % 13;
    }
    int64_t sum = 0;
    for (int i = 0; i < N_PARTICLES; ++i) {
        p[i].x += p[i].vx + 3;
        p[i].y += p[i].vy + 5;
        p[i].z += p[i].vz + 7;
        sum += p[i].x + p[i].y + p[i].z;
    }
    free(p);
    return sum;
}

static int64_t axpy_soa_unfused(void) {
    const size_t n = N_PARTICLES;
    int64_t *x = malloc(n * sizeof *x), *y = malloc(n * sizeof *y);
    int64_t *z = malloc(n * sizeof *z);
    int64_t *vx = malloc(n * sizeof *vx), *vy = malloc(n * sizeof *vy);
    int64_t *vz = malloc(n * sizeof *vz);
    for (size_t i = 0; i < n; ++i) {
        x[i] = i % 1000; y[i] = i % 997; z[i] = i % 991;
        vx[i] = i % 7; vy[i] = i % 11; vz[i] = i % 13;
    }
    for (size_t i = 0; i < n; ++i) {
        x[i] += vx[i] + 3; y[i] += vy[i] + 5; z[i] += vz[i] + 7;
    }
    int64_t sum = 0;
    for (size_t i = 0; i < n; ++i) sum += x[i] + y[i] + z[i];
    free(x); free(y); free(z); free(vx); free(vy); free(vz);
    return sum;
}

static int64_t axpy_soa_fused(void) {
    const size_t n = N_PARTICLES;
    int64_t *x = malloc(n * sizeof *x), *y = malloc(n * sizeof *y);
    int64_t *z = malloc(n * sizeof *z);
    for (size_t i = 0; i < n; ++i) {
        x[i] = (int64_t)(i % 1000) + (int64_t)(i % 7) + 3;
        y[i] = (int64_t)(i % 997) + (int64_t)(i % 11) + 5;
        z[i] = (int64_t)(i % 991) + (int64_t)(i % 13) + 7;
    }
    int64_t sum = 0;
    for (size_t i = 0; i < n; ++i) sum += x[i] + y[i] + z[i];
    free(x); free(y); free(z);
    return sum;
}

static int64_t *make_matrix(int n, int seed) {
    int64_t *m = calloc((size_t)n * n, sizeof(int64_t));
    for (int i = 0; i < n * n; ++i) m[i] = (i * 7 + seed) % 11;
    return m;
}

static int64_t matmul_ijk(int n, int64_t *a, int64_t *b, int64_t *c) {
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n; ++j)
            for (int k = 0; k < n; ++k)
                c[i * n + j] += a[i * n + k] * b[k * n + j];
    int64_t sum = 0;
    for (int i = 0; i < n * n; ++i) sum += c[i];
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

static int64_t matmul_omp_ijk(int n, int64_t *a, int64_t *b, int64_t *c) {
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n; ++j)
            for (int k = 0; k < n; ++k)
                c[i * n + j] += a[i * n + k] * b[k * n + j];
    int64_t sum = 0;
    for (int i = 0; i < n * n; ++i) sum += c[i];
    return sum;
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

static int64_t matmul_omp_ikj_simd(int n, int64_t *a, int64_t *b, int64_t *c) {
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        int64_t *ci = c + (size_t)i * n;
        const int64_t *ai = a + (size_t)i * n;
        for (int k = 0; k < n; ++k) {
            const int64_t aik = ai[k];
            const int64_t *bk = b + (size_t)k * n;
#pragma omp simd
            for (int j = 0; j < n; ++j) ci[j] += aik * bk[j];
        }
    }
    int64_t sum = 0;
    for (int i = 0; i < n * n; ++i) sum += c[i];
    return sum;
}

static int64_t sum_col(int n, int64_t *a) {
    int64_t sum = 0;
    for (int j = 0; j < n; ++j)
        for (int i = 0; i < n; ++i) sum += a[i * n + j];
    return sum;
}

static int64_t sum_row(int n, int64_t *a) {
    int64_t sum = 0;
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n; ++j) sum += a[i * n + j];
    return sum;
}

static int64_t sum_row4(int n, int64_t *a) {
    int64_t s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    const int len = n * n;
    int i = 0;
    for (; i + 4 <= len; i += 4) {
        s0 += a[i]; s1 += a[i + 1]; s2 += a[i + 2]; s3 += a[i + 3];
    }
    for (; i < len; ++i) s0 += a[i];
    return (s0 + s1) + (s2 + s3);
}

static int64_t *g_a, *g_b, *g_c, *g_grid;

static void bench(const char *name, int reps, int64_t (*fn)(void)) {
    double samples[16];
    int64_t checksum = 0;
    for (int r = 0; r < reps; ++r) {
        double t0 = now_ms();
        checksum = fn();
        samples[r] = now_ms() - t0;
    }
    for (int i = 1; i < reps; ++i)
        for (int j = i; j > 0 && samples[j - 1] > samples[j]; --j) {
            double tmp = samples[j]; samples[j] = samples[j - 1];
            samples[j - 1] = tmp;
        }
    printf("RESULT %s %.3f %lld\n", name, samples[reps / 2], (long long)checksum);
}

#define MATMUL_CASE(fn) \
    static int64_t fn##_case(void) { \
        for (int i = 0; i < MAT_N * MAT_N; ++i) g_c[i] = 0; \
        return fn(MAT_N, g_a, g_b, g_c); \
    }

MATMUL_CASE(matmul_ijk)
MATMUL_CASE(matmul_ikj)
MATMUL_CASE(matmul_omp_ijk)
MATMUL_CASE(matmul_omp_ikj)
MATMUL_CASE(matmul_omp_ikj_simd)

static int64_t sum_col_case(void) { return sum_col(GRID, g_grid); }
static int64_t sum_row_case(void) { return sum_row(GRID, g_grid); }
static int64_t sum_row4_case(void) { return sum_row4(GRID, g_grid); }

int main(void) {
    g_a = make_matrix(MAT_N, 1);
    g_b = make_matrix(MAT_N, 2);
    g_c = calloc((size_t)MAT_N * MAT_N, sizeof(int64_t));
    g_grid = make_matrix(GRID, 3);

    bench("axpy_aos", 5, axpy_aos);
    bench("axpy_aos_fused", 5, axpy_aos_fused);
    bench("axpy_soa", 5, axpy_soa_unfused);
    bench("axpy_soa_fused", 5, axpy_soa_fused);
    bench("matmul_ijk", 5, matmul_ijk_case);
    bench("matmul_ikj", 5, matmul_ikj_case);
    bench("matmul_omp_ijk", 5, matmul_omp_ijk_case);
    bench("matmul_omp_ikj", 5, matmul_omp_ikj_case);
    bench("matmul_omp_ikj_simd", 5, matmul_omp_ikj_simd_case);
    bench("sum_col", 5, sum_col_case);
    bench("sum_row", 5, sum_row_case);
    bench("sum_row4", 5, sum_row4_case);
    return 0;
}
