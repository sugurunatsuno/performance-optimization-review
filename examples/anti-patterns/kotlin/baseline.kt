// Kotlin (JVM) の典型的なアンチパターン（変更禁止）。
// build: kotlinc -include-runtime -d baseline.jar baseline.kt
// run:   java -Xms256m -Xmx1g -jar baseline.jar

import java.util.Locale

const val N = 320
const val GRID = 3000
const val NP = 2_000_000
const val ALLOC_OUTER = 50_000
const val ALLOC_INNER = 64
const val WARMUP = 2
const val REPS = 5

// AoS: 粒子 1 個 = オブジェクト 1 個（参照の配列をたどる）
data class Particle(
    var x: Long,
    var y: Long,
    var z: Long,
    var vx: Long,
    var vy: Long,
    var vz: Long,
)

fun makeMatrix(n: Int, seed: Long, mod: Long): LongArray =
    LongArray(n * n) { i -> (i * 7L + seed) % mod }

fun matmulIjk(a: LongArray, b: LongArray, c: LongArray) {
    for (i in 0 until N)
        for (j in 0 until N)
            for (k in 0 until N)
                c[i * N + j] += a[i * N + k] * b[k * N + j]
}

fun sum2dCol(a: LongArray): Long {
    var total = 0L
    for (j in 0 until GRID)
        for (i in 0 until GRID)
            total += a[i * GRID + j]
    return total
}

fun aos(): Long {
    val particles = Array(NP) { i ->
        Particle(
            (i % 1000).toLong(), (i % 997).toLong(), (i % 991).toLong(),
            (i % 7).toLong(), (i % 11).toLong(), (i % 13).toLong(),
        )
    }
    for (p in particles) {
        p.x += p.vx + 3
        p.y += p.vy + 5
        p.z += p.vz + 7
    }
    var total = 0L
    for (p in particles) total += p.x + p.y + p.z
    return total
}

fun alloc(): Long {
    var total = 0L
    for (i in 0 until ALLOC_OUTER) {
        val buffer = ArrayList<Int>()
        for (j in 0 until ALLOC_INNER) buffer.add((i + j) % 97)
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
        matmulIjk(a, b, c)
        c.sum()
    }
    bench("sum2d") { sum2dCol(grid) }
    bench("aos") { aos() }
    bench("alloc") { alloc() }
}
