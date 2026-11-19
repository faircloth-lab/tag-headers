import time
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from tag_headers.core import tag_headers

console = Console(stderr=True)
exists = click.Path(exists=True, dir_okay=False, path_type=Path)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--i1", required=True, type=exists, help="I1 (i7 index) FASTQ.")
@click.option("--i2", required=True, type=exists, help="I2 (random octamer) FASTQ.")
@click.option("--r1", required=True, type=exists, help="R1 FASTQ.")
@click.option("--r2", required=True, type=exists, help="R2 FASTQ.")
@click.option(
    "--out-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Output directory. Outputs keep the input R1/R2 file names.",
)
@click.option(
    "--total",
    type=int,
    default=None,
    help="Expected record count. Adds a percent bar and ETA; otherwise shows a running count.",
)
@click.option("--batch-size", type=int, default=50_000, show_default=True)
def main(i1, i2, r1, r2, out_dir, total, batch_size):
    """Append the I2 index to the I1 index in the R1/R2 FASTQ headers.

    Header comment 1:N:0:ACGT becomes 1:N:0:ACGT+TTGCAAGT. Reads are matched
    across all four files by ID; any mismatch aborts the run.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_r1, out_r2 = out_dir / r1.name, out_dir / r2.name
    if {out_r1.resolve(), out_r2.resolve()} & {r1.resolve(), r2.resolve()}:
        raise click.UsageError(
            "output would overwrite the input; choose a different --out-dir"
        )

    columns = [SpinnerColumn(), TextColumn("{task.description}")]
    if total:
        columns += [BarColumn(), MofNCompleteColumn()]
    else:
        columns += [TextColumn("{task.completed:,} records")]
    columns += [TimeElapsedColumn()]

    start = time.monotonic()
    with Progress(*columns, console=console, transient=True) as progress:
        task = progress.add_task("Tagging headers", total=total)
        try:
            n = tag_headers(
                i1,
                i2,
                r1,
                r2,
                out_r1,
                out_r2,
                on_batch=lambda k: progress.advance(task, k),
                batch_size=batch_size,
            )
        except (ValueError, RuntimeError) as e:
            raise click.ClickException(str(e))
    elapsed = time.monotonic() - start

    table = Table(title="tag-headers summary")
    table.add_column("Item")
    table.add_column("Value", justify="right")
    table.add_row("Records", f"{n:,}")
    table.add_row("Elapsed", f"{elapsed:.1f} s")
    table.add_row("Rate", f"{n / elapsed:,.0f} records/s" if elapsed else "n/a")
    table.add_row("Output R1", str(out_r1))
    table.add_row("Output R2", str(out_r2))
    console.print(table)
