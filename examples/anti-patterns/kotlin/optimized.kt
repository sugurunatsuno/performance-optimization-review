// Kotlin (JVM) 最適化版。RESULT 名・定数・checksum は baseline.kt と同一。
// build: kotlinc -include-runtime -d optimized.jar optimized.kt
// run:   java -Xms256m -Xmx1g -jar optimized.jar
//
// 変更点（すべて整数演算なので結果は厳密一致）:
//   matmul: i,j,k -> i,k,j（内側 j が連続アクセス）
//   sum2d : 列優先 -> 行優先（フラット走査）
//   aos   : AoS オブジェクト配列 -> SoA の LongArray、初期化と更新を融合
//   alloc : 毎回 ArrayList を確保 -> IntArray を 1 個再利用

import java.util.Locale

const val N = 320
const val GRID = 3000
const val NP = 2_000_000
const val ALLOC_OUTER = 50_000
const val ALLOC_INNER = 64
const val WARMUP = 2
const val REPS = 5

fun makeMatrix(n: Int, seed: Long, mod: Long): LongArray =
    LongArray(n * n) { i -> (i * 7L + seed) % mod }

fun matmulIkj(a: LongArray, b: LongArray, c: LongArray) {
    for (i in 0 until N) {
        val ci = i * N
        for (k in 0 until N) {
            val aik = a[ci + k]
            val bk = k * N
            for (j in 0 until N) c[ci + j] += aik * b[bk + j]
        }
    }
}

fun sum2dRow(a: LongArray): Long {
    var total = 0L
    for (v in a) total += v
    return total
}

fun aos(): Long {
    // v は更新後どこからも読まれないので、式に畳み込んで配列に持たない。
    val x = LongArray(NP) { i -> (i % 1000).toLong() + (i % 7).toLong() + 3 }
    val y = LongArray(NP) { i -> (i % 997).toLong() + (i % 11).toLong() + 5 }
    val z = LongArray(NP) { i -> (i % 991).toLong() + (i % 13).toLong() + 7 }
    var total = 0L
    for (i in 0 until NP) total += x[i] + y[i] + z[i]
    return total
}

fun alloc(): Long {
    var total = 0L
    val buffer = IntArray(ALLOC_INNER)
    for (i in 0 until ALLOC_OUTER) {
        for (j in 0 until ALLOC_INNER) buffer[j] = (i + j) % 97
        for (v in buffer) total += v
    }
    return total
}

fun bench(name: String, f: () -> Long) {
    var checksum = 0L
    repeat(WARMUP) { checksum = f() }
    val samples = DoubleArray(REPS)
    for (r in 0 until REPS) {
        val t0 = System.nanoTime()
        checksum = f()
        samples[r] = (System.nanoTime() - t0) / 1_000_000.0
    }
    samples.sort()
    val median = String.format(Locale.ROOT, "%.3f", samples[REPS / 2])
    println("RESULT $name $median $checksum")
}

fun main() {
    val a = makeMatrix(N, 1, 11L)
    val b = makeMatrix(N, 2, 11L)
    val c = LongArray(N * N)
    val grid = makeMatrix(GRID, 3, 101L)

    bench("matmul") {
        c.fill(0)
        matmulIkj(a, b, c)
        c.sum()
    }
    bench("sum2d") { sum2dRow(grid) }
    bench("aos") { aos() }
    bench("alloc") { alloc() }
}
