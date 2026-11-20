// JDK 21。最適化版（Baseline と同じ出力・チェックサム）。
import java.util.Arrays;
import java.util.function.LongSupplier;

public class Optimized {
    static final int N = 320;
    static final int GRID = 3000;
    static final int NP = 2_000_000;
    static final int ALLOC_OUTER = 50_000;
    static final int ALLOC_INNER = 64;
    static final int WARMUP = 2;
    static final int REPS = 5;

    static final int[] X = new int[NP], Y = new int[NP], Z = new int[NP];
    static final int[] VX = new int[NP], VY = new int[NP], VZ = new int[NP];

    static int[] matrix(int n, int seed) {
        int[] m = new int[n * n];
        for (int i = 0; i < m.length; i++) {
            m[i] = (i * 7 + seed) % 11;
        }
        return m;
    }

    static int[] gridData() {
        int[] g = new int[GRID * GRID];
        for (int i = 0; i < g.length; i++) {
            g[i] = (i * 7 + 3) % 101;
        }
        return g;
    }

    static void initParticles() {
        for (int i = 0; i < NP; i++) {
            X[i] = i % 1000;
            Y[i] = i % 997;
            Z[i] = i % 991;
            VX[i] = i % 7;
            VY[i] = i % 11;
            VZ[i] = i % 13;
        }
    }

    static void matmul(int[] a, int[] b, int[] c) {
        for (int i = 0; i < N; i++) {
            int rowC = i * N;
            for (int k = 0; k < N; k++) {
                int aik = a[i * N + k];
                int rowB = k * N;
                for (int j = 0; j < N; j++) {
                    c[rowC + j] += aik * b[rowB + j];
                }
            }
        }
    }

    static long sum2dRowMajor(int[] g) {
        long total = 0;
        for (int i = 0; i < GRID; i++) {
            int row = i * GRID;
            for (int j = 0; j < GRID; j++) {
                total += g[row + j];
            }
        }
        return total;
    }

    static long updateParticles() {
        long total = 0;
        for (int i = 0; i < NP; i++) {
            X[i] += VX[i] + 3;
            Y[i] += VY[i] + 5;
            Z[i] += VZ[i] + 7;
            total += X[i] + Y[i] + Z[i];
        }
        return total;
    }

    static long allocReusedBuffer() {
        int[] row = new int[ALLOC_INNER];
        long total = 0;
        for (int i = 0; i < ALLOC_OUTER; i++) {
            for (int j = 0; j < ALLOC_INNER; j++) {
                row[j] = (i + j) % 97;
            }
            for (int j = 0; j < ALLOC_INNER; j++) {
                total += row[j];
            }
        }
        return total;
    }

    static void bench(String name, LongSupplier caseRun) {
        for (int i = 0; i < WARMUP; i++) {
            caseRun.getAsLong();
        }
        long[] samples = new long[REPS];
        long checksum = 0;
        for (int r = 0; r < REPS; r++) {
            long start = System.nanoTime();
            checksum = caseRun.getAsLong();
            samples[r] = System.nanoTime() - start;
        }
        Arrays.sort(samples);
        System.out.printf("RESULT %s %.3f %d%n", name, samples[REPS / 2] / 1e6, checksum);
    }

    public static void main(String[] args) {
        int[] a = matrix(N, 1);
        int[] b = matrix(N, 2);
        int[] c = new int[N * N];
        int[] grid = gridData();

        bench("matmul", () -> {
            Arrays.fill(c, 0);
            matmul(a, b, c);
            long sum = 0;
            for (int v : c) {
                sum += v;
            }
            return sum;
        });
        bench("sum2d", () -> sum2dRowMajor(grid));
        bench("aos", () -> {
            initParticles();
            return updateParticles();
        });
        bench("alloc", Optimized::allocReusedBuffer);
    }
}
