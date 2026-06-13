from collections.abc import Iterable
from pathlib import Path
import os

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel


def write_models(path: Path, records: Iterable[BaseModel], batch_size: int = 1000) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    writer: pq.ParquetWriter | None = None
    batch: list[dict] = []
    count = 0
    try:
        for record in records:
            batch.append(record.model_dump(mode="python"))
            if len(batch) >= batch_size:
                table = pa.Table.from_pylist(batch)
                writer = writer or pq.ParquetWriter(temporary_path, table.schema, compression="zstd")
                writer.write_table(table)
                count += len(batch)
                batch.clear()
        if batch:
            table = pa.Table.from_pylist(batch)
            writer = writer or pq.ParquetWriter(temporary_path, table.schema, compression="zstd")
            writer.write_table(table)
            count += len(batch)
    finally:
        if writer:
            writer.close()
    if writer is None:
        raise ValueError(f"Cannot write an empty Parquet dataset: {path}")
    os.replace(temporary_path, path)
    return count


def write_rows(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows), temporary_path, compression="zstd")
    os.replace(temporary_path, path)
    return len(rows)
