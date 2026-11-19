import gzip
from pathlib import Path

import pytest
from click.testing import CliRunner

from tag_headers.cli import main
from tag_headers.core import tag_headers


def write(path: Path, records):
    with gzip.open(path, "wt") as f:
        for r in records:
            f.write("\n".join(r) + "\n")


def make(tmp_path, ids=("r1", "r2"), i2_ids=None):
    i2_ids = i2_ids or ids
    paths = {k: tmp_path / f"{k}.fastq.gz" for k in ("i1", "i2", "r1", "r2")}
    write(
        paths["i1"],
        [(f"@{i} 1:N:0:AAAAAAAA", "AAAAAAAA", "+", "IIIIIIII") for i in ids],
    )
    write(
        paths["i2"],
        [(f"@{i} 2:N:0:AAAAAAAA", "CCCCCCCC", "+", "IIIIIIII") for i in i2_ids],
    )
    write(paths["r1"], [(f"@{i} 1:N:0:AAAAAAAA", "ACGT", "+", "IIII") for i in ids])
    write(paths["r2"], [(f"@{i} 2:N:0:AAAAAAAA", "TGCA", "+", "IIII") for i in ids])
    return paths


def test_tags_headers(tmp_path):
    p = make(tmp_path)
    calls = []
    n = tag_headers(
        p["i1"],
        p["i2"],
        p["r1"],
        p["r2"],
        tmp_path / "o1.fastq.gz",
        tmp_path / "o2.fastq.gz",
        on_batch=calls.append,
        batch_size=1,
    )
    assert n == 2 and calls == [1, 1]
    with gzip.open(tmp_path / "o1.fastq.gz", "rt") as f:
        lines = f.read().splitlines()
    assert lines[:4] == ["@r1 1:N:0:AAAAAAAA+CCCCCCCC", "ACGT", "+", "IIII"]
    with gzip.open(tmp_path / "o2.fastq.gz", "rt") as f:
        assert f.readline().strip() == "@r1 2:N:0:AAAAAAAA+CCCCCCCC"


def test_id_mismatch(tmp_path):
    p = make(tmp_path, i2_ids=("r1", "x"))
    with pytest.raises(ValueError, match="mismatch"):
        tag_headers(
            p["i1"], p["i2"], p["r1"], p["r2"], tmp_path / "o1.gz", tmp_path / "o2.gz"
        )


def test_count_mismatch(tmp_path):
    p = make(tmp_path)
    write(p["i2"], [("@r1 2:N:0:A", "CCCCCCCC", "+", "IIIIIIII")])
    with pytest.raises(ValueError, match="record counts"):
        tag_headers(
            p["i1"], p["i2"], p["r1"], p["r2"], tmp_path / "o1.gz", tmp_path / "o2.gz"
        )


def test_cli(tmp_path):
    p = make(tmp_path)
    out = tmp_path / "out"
    res = CliRunner().invoke(
        main, [f"--{k}={v}" for k, v in p.items()] + [f"--out-dir={out}"]
    )
    assert res.exit_code == 0, res.output
    assert (out / "r1.fastq.gz").exists()
