ALTER TABLE invalid_records ADD COLUMN natural_key TEXT;
ALTER TABLE invalid_records ADD COLUMN invalid_value TEXT;
ALTER TABLE invalid_records ADD COLUMN severity TEXT NOT NULL DEFAULT 'fatal';
ALTER TABLE invalid_records ADD COLUMN validation_version TEXT NOT NULL DEFAULT 'v1';

CREATE INDEX IF NOT EXISTS idx_invalid_records_field ON invalid_records(source, field_name, error_type);
