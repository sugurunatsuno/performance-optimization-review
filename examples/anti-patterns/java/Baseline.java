// JDK 21。アンチパターン版（変更禁止）。
import java.util.ArrayList;
import java.util.Arrays;
import java.util.function.LongSupplier;

public class Baseline {
    static final int N = 320;
    static final int GRID = 3000;
    static final int NP = 2_000_000;
    static final int ALLOC_OUTER = 50_000;
    static final int ALLOC_INNER = 64;
    static final int WARMUP = 2;
    static final int REPS = 5;

    static final class Particle {
        long x, y, z, vx, vy, vz;
    }

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

    static Particle[] particles() {
        Particle[] p = new Particle[NP];
        for (int i = 0; i < NP; i++) {
            Particle q = new Particle();
            q.x = i % 1000;
            q.y = i % 997;
            q.z = i % 991;
            q.vx = i % 7;
            q.vy = i % 11;
            q.vz = i % 13;
            p[i] = q;
        }
        return p;
    }

    static void matmul(int[] a, int[] b, int[] c) {
        for (int i = 0; i < N; i++)
            for (int j = 0; j < N; j++)
                for (int k = 0; k < N; k++)
                    c[i * N + j] += a[i * N + k] * b[k * N + j];
    }

    static long sum2dColumnMajor(int[] g) {
        long total = 0;
        for (int j = 0; j < GRID; j++)
            for (int i = 0; i < GRID; i++)
                total += g[i * GRID + j];
        return total;
    }

    static long updateParticles(Particle[] p) {
        long total = 0;
        for (Particle q : p) {
            q.x += q.vx + 3;
            q.y += q.vy + 5;
            q.z += q.vz + 7;
            total += q.x + q.y + q.z;
        }
        return total;
    }

    static long allocPerIteration() {
        long total = 0;
        for (int i = 0; i < ALLOC_OUTER; i++) {
            ArrayList<Integer> row = new ArrayList<>(ALLOC_INNER);
            for (int j = 0; j < ALLOC_INNER; j++) {
                row.add((i + j) % 97);
            }
            for (int v : row) {
                total += v;
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
        bench("sum2d", () -> sum2dColumnMajor(grid));
        bench("aos", () -> updateParticles(particles()));
        bench("alloc", Baseline::allocPerIteration);
    }
}
