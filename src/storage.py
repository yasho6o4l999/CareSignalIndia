from collections.abc import Iterable
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel


def write_models(path: Path, records: Iterable[BaseModel], batch_size: int = 1000) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    batch: list[dict] = []
    count = 0
    try:
        for record in records:
            batch.append(record.model_dump(mode="python"))
            if len(batch) >= batch_size:
                table = pa.Table.from_pylist(batch)
                writer = writer or pq.ParquetWriter(path, table.schema, compression="zstd")
                writer.write_table(table)
                count += len(batch)
                batch.clear()
        if batch:
            table = pa.Table.from_pylist(batch)
            writer = writer or pq.ParquetWriter(path, table.schema, compression="zstd")
            writer.write_table(table)
            count += len(batch)
    finally:
        if writer:
            writer.close()
    return count


def write_rows(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
    return len(rows)

