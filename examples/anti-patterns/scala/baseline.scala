// Scala の典型的なアンチパターン（変更禁止）。
// build: scalac -d out baseline.scala && java -cp out... Baseline

object Baseline:
  val N = 320
  val GRID = 3000
  val NP = 2_000_000
  val ALLOC_OUTER = 50_000
  val ALLOC_INNER = 64
  val WARMUP = 2
  val REPS = 5

  final case class Particle(var x: Long, var y: Long, var z: Long,
                            var vx: Long, var vy: Long, var vz: Long)

  def makeMatrix(n: Int, seed: Long, mod: Long): Array[Long] =
    val m = new Array[Long](n * n)
    var i = 0
    while i < m.length do
      m(i) = (i * 7 + seed) % mod
      i += 1
    m

  // i-j-k: k 方向の b アクセスが列ストライドになる。
  def matmul(a: Array[Long], b: Array[Long], c: Array[Long]): Long =
    java.util.Arrays.fill(c, 0L)
    var i = 0
    while i < N do
      var j = 0
      while j < N do
        var k = 0
        while k < N do
          c(i * N + j) += a(i * N + k) * b(k * N + j)
          k += 1
        j += 1
      i += 1
    var sum = 0L
    i = 0
    while i < c.length do
      sum += c(i)
      i += 1
    sum

  // 列優先: row-major のフラット配列を列方向に走査する。
  def sum2d(v: Array[Long]): Long =
    var sum = 0L
    var j = 0
    while j < GRID do
      var i = 0
      while i < GRID do
        sum += v(i * GRID + j)
        i += 1
      j += 1
    sum

  // 構造体配列 (AoS): 更新のたびにキャッシュラインを跨いで 6 フィールドを読む。
  def aos(): Long =
    val ps = new Array[Particle](NP)
    var i = 0
    while i < NP do
      ps(i) = Particle(i % 1000, i % 997, i % 991, i % 7, i % 11, i % 13)
      i += 1
    i = 0
    while i < NP do
      val p = ps(i)
      p.x += p.vx + 3
      p.y += p.vy + 5
      p.z += p.vz + 7
      i += 1
    var sum = 0L
    i = 0
    while i < NP do
      val p = ps(i)
      sum += p.x + p.y + p.z
      i += 1
    sum

  // 外側ループのたびに新しい配列を確保する。
  // lastBuffer への 1 回の volatile 代入で確保を JIT のエスケープ解析から守る。
  @volatile private var lastBuffer: Array[Int] = null

  def alloc(): Long =
    var total = 0L
    var last: Array[Int] = null
    var i = 0
    while i < ALLOC_OUTER do
      val buf = new Array[Int](ALLOC_INNER)
      last = buf
      var j = 0
      while j < ALLOC_INNER do
        buf(j) = (i + j) % 97
        j += 1
      j = 0
      while j < ALLOC_INNER do
        total += buf(j)
        j += 1
      i += 1
    lastBuffer = last
    total

  def bench(name: String)(run: => Long): Unit =
    var w = 0
    while w < WARMUP do
      run
      w += 1
    val samples = new Array[Long](REPS)
    var checksum = 0L
    var r = 0
    while r < REPS do
      val t0 = System.nanoTime()
      checksum = run
      samples(r) = System.nanoTime() - t0
      r += 1
    java.util.Arrays.sort(samples)
    println(String.format(java.util.Locale.ROOT, "RESULT %s %.3f %d",
      name, samples(REPS / 2) / 1e6, Long.box(checksum)))

  def main(args: Array[String]): Unit =
    val a = makeMatrix(N, 1, 11)
    val b = makeMatrix(N, 2, 11)
    val c = new Array[Long](N * N)
    val grid = makeMatrix(GRID, 3, 101)

    bench("matmul")(matmul(a, b, c))
    bench("sum2d")(sum2d(grid))
    bench("aos")(aos())
    bench("alloc")(alloc())
