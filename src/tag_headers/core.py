import gzip
import shutil
import subprocess
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import IO

BATCH_SIZE = 50_000


def open_in(path: Path) -> tuple[IO[str], subprocess.Popen | None]:
    if path.suffix != ".gz":
        return open(path), None
    if shutil.which("pigz"):
        proc = subprocess.Popen(
            ["pigz", "-dc", str(path)],
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1 << 20,
        )
        return proc.stdout, proc
    return gzip.open(path, "rt"), None


def open_out(
    path: Path, threads: int | None = None
) -> tuple[IO[str], subprocess.Popen | None, IO[bytes] | None]:
    if path.suffix != ".gz":
        return open(path, "w"), None, None
    if shutil.which("pigz"):
        raw = open(path, "wb")  # noqa: SIM115
        proc = subprocess.Popen(
            ["pigz", "-c"],
            stdin=subprocess.PIPE,
            stdout=raw,
            text=True,
            bufsize=1 << 20,
        )
        return proc.stdin, proc, raw
    return gzip.open(path, "wt"), None, None


def read_record(f: IO[str]) -> tuple[str, str, str, str] | None:
    header = f.readline()
    if not header:
        return None
    return header.rstrip("\n"), f.readline().rstrip("\n"), f.readline(), f.readline()


def tag_record(rec: tuple[str, str, str, str], index: str) -> str:
    name, _, comment = rec[0].partition(" ")
    prefix = comment.rsplit(":", 1)[0] if comment else "1:N:0"
    return f"{name} {prefix}:{index}\n{rec[1]}\n{rec[2]}{rec[3]}"


def tag_headers(
    i1: Path,
    i2: Path,
    r1: Path,
    r2: Path,
    out_r1: Path,
    out_r2: Path,
    on_batch: Callable[[int], None] | None = None,
    batch_size: int = BATCH_SIZE,
    threads: int | None = None,
) -> int:
    """Rewrite R1/R2 headers so the index field is I1+I2. Returns the record count.

    threads is the total CPU budget; each of the two pigz compressors gets half.
    """
    per_writer = max(1, threads // 2) if threads else None
    n = 0
    with ExitStack() as stack:
        procs = []
        readers = []
        for p in (i1, i2, r1, r2):
            f, proc = open_in(p)
            stack.callback(f.close)
            readers.append(f)
            if proc:
                procs.append(proc)
        writers = []
        for p in (out_r1, out_r2):
            f, proc, raw = open_out(p, per_writer)
            writers.append(f)
            if proc:
                procs.append(proc)
            if raw:
                stack.callback(raw.close)
        i1f, i2f, r1f, r2f = readers
        w1, w2 = writers
        pending = 0
        while True:
            a, b, c, d = (read_record(f) for f in (i1f, i2f, r1f, r2f))
            recs = (a, b, c, d)
            if any(x is None for x in recs):
                if not all(x is None for x in recs):
                    raise ValueError(
                        f"input files have different record counts (ended at {n})"
                    )
                break
            ids = {x[0].split(" ")[0] for x in (a, b, c, d)}
            if len(ids) != 1:
                raise ValueError(f"read ID mismatch at record {n + 1}: {sorted(ids)}")
            index = f"{a[1]}+{b[1]}"
            w1.write(tag_record(c, index))
            w2.write(tag_record(d, index))
            n += 1
            pending += 1
            if pending == batch_size:
                if on_batch:
                    on_batch(pending)
                pending = 0
        if pending and on_batch:
            on_batch(pending)
        for w in writers:
            w.close()
        for proc in procs:
            if proc.wait() != 0:
                raise RuntimeError(f"pigz exited with status {proc.returncode}")
    return n
