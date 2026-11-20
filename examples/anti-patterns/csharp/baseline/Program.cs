// C# の典型的なアンチパターン（変更禁止）。
// build: dotnet build -c Release

using System.Diagnostics;
using System.Globalization;

namespace Baseline;

internal static class Program
{
    private const int N = 320;
    private const int GRID = 3000;
    private const int NP = 2_000_000;
    private const int ALLOC_OUTER = 50_000;
    private const int ALLOC_INNER = 64;
    private const int WARMUP = 2;
    private const int REPS = 5;

    private struct Particle
    {
        public long X, Y, Z, Vx, Vy, Vz;
    }

    private static readonly int[] A = MakeMatrix(N, 1);
    private static readonly int[] B = MakeMatrix(N, 2);
    private static readonly int[] C = new int[N * N];
    private static readonly int[] Grid = MakeGrid(GRID);
    private static readonly Particle[] Particles = new Particle[NP];

    private static int[] MakeMatrix(int n, int seed)
    {
        var data = new int[n * n];
        for (int i = 0; i < data.Length; i++)
            data[i] = (i * 7 + seed) % 11;
        return data;
    }

    private static int[] MakeGrid(int n)
    {
        var data = new int[n * n];
        for (int i = 0; i < data.Length; i++)
            data[i] = (i * 7 + 3) % 101;
        return data;
    }

    // i-j-k: 内側 k が B を列方向に飛ばして読み、C の同じ要素を繰り返し更新する。
    private static long MatMul()
    {
        Array.Clear(C);
        for (int i = 0; i < N; i++)
            for (int j = 0; j < N; j++)
                for (int k = 0; k < N; k++)
                    C[i * N + j] += A[i * N + k] * B[k * N + j];

        long sum = 0;
        foreach (int v in C)
            sum += v;
        return sum;
    }

    // 列優先: 行優先の配列を 1 要素ずつ飛ばして読む。
    private static long Sum2D()
    {
        long total = 0;
        for (int j = 0; j < GRID; j++)
            for (int i = 0; i < GRID; i++)
                total += Grid[i * GRID + j];
        return total;
    }

    // AoS: 6 つの long が 1 要素に並ぶため、更新と総和で 48 バイト間隔に触れる。
    private static long Aos()
    {
        for (int i = 0; i < NP; i++)
        {
            Particles[i].X = i % 1000;
            Particles[i].Y = i % 997;
            Particles[i].Z = i % 991;
            Particles[i].Vx = i % 7;
            Particles[i].Vy = i % 11;
            Particles[i].Vz = i % 13;
        }

        for (int i = 0; i < NP; i++)
        {
            Particles[i].X += Particles[i].Vx + 3;
            Particles[i].Y += Particles[i].Vy + 5;
            Particles[i].Z += Particles[i].Vz + 7;
        }

        long sum = 0;
        for (int i = 0; i < NP; i++)
            sum += Particles[i].X + Particles[i].Y + Particles[i].Z;
        return sum;
    }

    // 外側ループのたびに新しい配列を確保する。
    private static long Alloc()
    {
        long total = 0;
        for (int i = 0; i < ALLOC_OUTER; i++)
        {
            var buffer = new int[ALLOC_INNER];
            for (int j = 0; j < ALLOC_INNER; j++)
                buffer[j] = (i + j) % 97;
            foreach (int v in buffer)
                total += v;
        }
        return total;
    }

    private static void Bench(string name, Func<long> fn)
    {
        for (int i = 0; i < WARMUP; i++)
            fn();

        var samples = new double[REPS];
        long checksum = 0;
        for (int r = 0; r < REPS; r++)
        {
            var sw = Stopwatch.StartNew();
            checksum = fn();
            sw.Stop();
            samples[r] = sw.Elapsed.TotalMilliseconds;
        }

        Array.Sort(samples);
        Console.WriteLine(
            string.Create(CultureInfo.InvariantCulture,
                $"RESULT {name} {samples[REPS / 2]:F3} {checksum}"));
    }

    private static void Main()
    {
        Bench("matmul", MatMul);
        Bench("sum2d", Sum2D);
        Bench("aos", Aos);
        Bench("alloc", Alloc);
    }
}
