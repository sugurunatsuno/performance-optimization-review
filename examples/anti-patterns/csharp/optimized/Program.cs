// C# の典型的なアンチパターンを修正した版。
// build: dotnet build -c Release

using System.Diagnostics;
using System.Globalization;

namespace Optimized;

internal static class Program
{
    private const int N = 320;
    private const int GRID = 3000;
    private const int NP = 2_000_000;
    private const int ALLOC_OUTER = 50_000;
    private const int ALLOC_INNER = 64;
    private const int WARMUP = 2;
    private const int REPS = 5;

    private static readonly int[] A = MakeMatrix(N, 1);
    private static readonly int[] B = MakeMatrix(N, 2);
    private static readonly int[] C = new int[N * N];
    private static readonly int[] Grid = MakeGrid(GRID);
    private static readonly int[] AllocBuffer = new int[ALLOC_INNER];

    // SoA: フィールドごとに連続した配列を用意する。
    private static readonly long[] X = new long[NP];
    private static readonly long[] Y = new long[NP];
    private static readonly long[] Z = new long[NP];
    private static readonly long[] Vx = new long[NP];
    private static readonly long[] Vy = new long[NP];
    private static readonly long[] Vz = new long[NP];

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

    // i-k-j: 内側 j が B と C の連続領域を走査する。各要素の値は同じで総和も同一。
    private static long MatMul()
    {
        Array.Clear(C);
        for (int i = 0; i < N; i++)
        {
            var arow = A.AsSpan(i * N, N);
            var crow = C.AsSpan(i * N, N);
            for (int k = 0; k < N; k++)
            {
                int aik = arow[k];
                var brow = B.AsSpan(k * N, N);
                for (int j = 0; j < N; j++)
                    crow[j] += aik * brow[j];
            }
        }

        long sum = 0;
        foreach (int v in C)
            sum += v;
        return sum;
    }

    // 行優先のバッファなので、連続する列を内側にする。
    private static long Sum2D()
    {
        long total = 0;
        for (int i = 0; i < GRID; i++)
        {
            int row = i * GRID;
            for (int j = 0; j < GRID; j++)
                total += Grid[row + j];
        }
        return total;
    }

    // フィールドごとに連続した配列を走査し、更新と総和を 1 パスに融合する。
    private static long Aos()
    {
        for (int i = 0; i < NP; i++)
        {
            X[i] = i % 1000;
            Y[i] = i % 997;
            Z[i] = i % 991;
            Vx[i] = i % 7;
            Vy[i] = i % 11;
            Vz[i] = i % 13;
        }

        long sum = 0;
        for (int i = 0; i < NP; i++)
        {
            X[i] += Vx[i] + 3;
            Y[i] += Vy[i] + 5;
            Z[i] += Vz[i] + 7;
            sum += X[i] + Y[i] + Z[i];
        }
        return sum;
    }

    // ループ外で確保したバッファを使い回す。
    private static long Alloc()
    {
        long total = 0;
        for (int i = 0; i < ALLOC_OUTER; i++)
        {
            for (int j = 0; j < ALLOC_INNER; j++)
                AllocBuffer[j] = (i + j) % 97;
            foreach (int v in AllocBuffer)
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
