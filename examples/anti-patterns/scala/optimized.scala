// Scala の典型的なアンチパターンを修正した版。
// build: scalac -d out optimized.scala && java -cp out... Optimized

object Optimized:
  val N = 320
  val GRID = 3000
  val NP = 2_000_000
  val ALLOC_OUTER = 50_000
  val ALLOC_INNER = 64
  val WARMUP = 2
  val REPS = 5

  def makeMatrix(n: Int, seed: Long, mod: Long): Array[Long] =
    val m = new Array[Long](n * n)
    var i = 0
    while i < m.length do
      m(i) = (i * 7 + seed) % mod
      i += 1
    m

  // i-k-j: 内側 j が b / c の連続領域を走査する。c の各要素への加算順は
  // k 昇順のままで、整数の総和は元の i-j-k と同一。
  def matmul(a: Array[Long], b: Array[Long], c: Array[Long]): Long =
    java.util.Arrays.fill(c, 0L)
    var i = 0
    while i < N do
      val aRow = i * N
      val cRow = i * N
      var k = 0
      while k < N do
        val aik = a(aRow + k)
        val bRow = k * N
        var j = 0
        while j < N do
          c(cRow + j) += aik * b(bRow + j)
          j += 1
        k += 1
      i += 1
    var sum = 0L
    i = 0
    while i < c.length do
      sum += c(i)
      i += 1
    sum

  // 行優先: 連続する要素を順に走査する。
  def sum2d(v: Array[Long]): Long =
    var sum = 0L
    var i = 0
    while i < GRID do
      var j = 0
      while j < GRID do
        sum += v(i * GRID + j)
        j += 1
      i += 1
    sum

  // SoA: フィールドごとに連続したプリミティブ配列を走査し、更新と総和を 1 パスに融合。
  def aos(): Long =
    val xs = new Array[Long](NP)
    val ys = new Array[Long](NP)
    val zs = new Array[Long](NP)
    val vxs = new Array[Long](NP)
    val vys = new Array[Long](NP)
    val vzs = new Array[Long](NP)
    var i = 0
    while i < NP do
      xs(i) = i % 1000
      ys(i) = i % 997
      zs(i) = i % 991
      vxs(i) = i % 7
      vys(i) = i % 11
      vzs(i) = i % 13
      i += 1
    var sum = 0L
    i = 0
    while i < NP do
      val x = xs(i) + vxs(i) + 3
      val y = ys(i) + vys(i) + 5
      val z = zs(i) + vzs(i) + 7
      xs(i) = x
      ys(i) = y
      zs(i) = z
      sum += x + y + z
      i += 1
    sum

  // 配列をループ外で 1 個だけ確保して再利用する。
  def alloc(): Long =
    val buf = new Array[Int](ALLOC_INNER)
    var total = 0L
    var i = 0
    while i < ALLOC_OUTER do
      var j = 0
      while j < ALLOC_INNER do
        buf(j) = (i + j) % 97
        j += 1
      j = 0
      while j < ALLOC_INNER do
        total += buf(j)
        j += 1
      i += 1
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
