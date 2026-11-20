/* C の典型的なアンチパターン（変更禁止）。
 * build: gcc -O3 -fopenmp baseline.c -o baseline
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
        p[i].x = i % 1000;
        p[i].y = i % 997;
        p[i].z = i % 991;
        p[i].vx = i % 7;
        p[i].vy = i % 11;
        p[i].vz = i % 13;
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

static int64_t matmul_ijk(int n, int64_t *a, int64_t *b, int64_t *c) {
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n; ++j)
            for (int k = 0; k < n; ++k)
                c[i * n + j] += a[i * n + k] * b[k * n + j];
    int64_t sum = 0;
    for (int i = 0; i < n * n; ++i) sum += c[i];
    return sum;
}

static int64_t sum2d_col(int n, int64_t *a) {
    int64_t sum = 0;
    for (int j = 0; j < n; ++j)
        for (int i = 0; i < n; ++i) sum += a[i * n + j];
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
    return matmul_ijk(MAT_N, g_a, g_b, g_c);
}

static int64_t once_sum2d(void) { return sum2d_col(GRID, g_grid); }

static int64_t once_matmul_omp(void) {
    for (int i = 0; i < MAT_N * MAT_N; ++i) g_c[i] = 0;
    return matmul_omp_ijk(MAT_N, g_a, g_b, g_c);
}

int main(void) {
    g_a = make_matrix(MAT_N, 1);
    g_b = make_matrix(MAT_N, 2);
    g_c = calloc((size_t)MAT_N * MAT_N, sizeof(int64_t));
    g_grid = make_matrix(GRID, 3);
    double med;

    run("axpy", &med, 3, axpy_aos);
    run("matmul", &med, 3, once_matmul);
    run("sum2d", &med, 3, once_sum2d);
    run("matmul_omp", &med, 3, once_matmul_omp);
    return 0;
}
