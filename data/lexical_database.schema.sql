-- Stable, source-faithful lexical database schema.  BAdW text is imported
-- only into ignored local databases; this schema itself contains no source text.
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE source_snapshot (
  id TEXT PRIMARY KEY, collection_id TEXT NOT NULL, input_sha256 TEXT NOT NULL,
  records_manifest_sha256 TEXT, observed_at TEXT
);
CREATE TABLE source_object (
  snapshot_id TEXT NOT NULL REFERENCES source_snapshot(id), source_id TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, stable_url TEXT, PRIMARY KEY (snapshot_id, source_id)
);
CREATE TABLE lexical_record (
  id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES source_snapshot(id),
  record_type TEXT NOT NULL, extraction_run_id TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE record_source_span (
  record_id TEXT NOT NULL REFERENCES lexical_record(id), ordinal INTEGER NOT NULL,
  snapshot_id TEXT NOT NULL, source_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
  field TEXT NOT NULL, start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL,
  PRIMARY KEY (record_id, ordinal),
  FOREIGN KEY (snapshot_id, source_id) REFERENCES source_object(snapshot_id, source_id)
);
CREATE TABLE entry (
  id TEXT PRIMARY KEY REFERENCES lexical_record(id), layer TEXT NOT NULL,
  loc_headword TEXT NOT NULL, tibetan_headword TEXT NOT NULL, homonym TEXT NOT NULL,
  stable_url TEXT NOT NULL
);
CREATE TABLE sense (
  id TEXT PRIMARY KEY REFERENCES lexical_record(id), entry_id TEXT NOT NULL REFERENCES entry(id),
  ordinal INTEGER NOT NULL, source_label TEXT NOT NULL, definition TEXT NOT NULL
);
CREATE TABLE citation (
  id TEXT PRIMARY KEY REFERENCES lexical_record(id), entry_id TEXT NOT NULL REFERENCES entry(id),
  raw_text TEXT NOT NULL, siglum TEXT, locator TEXT, authority_status TEXT NOT NULL,
  bibliographic_source_id TEXT
);
CREATE TABLE attestation (
  id TEXT PRIMARY KEY REFERENCES lexical_record(id), entry_id TEXT NOT NULL REFERENCES entry(id),
  sense_id TEXT REFERENCES sense(id), ordinal INTEGER NOT NULL, association_status TEXT NOT NULL,
  tibetan TEXT NOT NULL, german_translation TEXT NOT NULL
);
CREATE TABLE attestation_citation (
  attestation_id TEXT NOT NULL REFERENCES attestation(id), citation_id TEXT NOT NULL REFERENCES citation(id),
  PRIMARY KEY (attestation_id, citation_id)
);
CREATE TABLE cross_reference (
  id TEXT PRIMARY KEY REFERENCES lexical_record(id), entry_id TEXT NOT NULL REFERENCES entry(id),
  marker TEXT NOT NULL, target_label TEXT, target_url TEXT, resolution_status TEXT NOT NULL
);
CREATE TABLE bibliographic_source (
  id TEXT PRIMARY KEY, canonical_label TEXT NOT NULL, work_title TEXT, intro_line_ref TEXT,
  source_kind TEXT NOT NULL, registry_status TEXT
);
CREATE TABLE bibliographic_alias (
  bibliographic_source_id TEXT NOT NULL REFERENCES bibliographic_source(id), alias TEXT NOT NULL,
  alias_kind TEXT NOT NULL, normalized_alias TEXT NOT NULL,
  PRIMARY KEY (bibliographic_source_id, alias, alias_kind)
);
CREATE TABLE citation_authority_candidate (
  citation_id TEXT NOT NULL REFERENCES citation(id),
  bibliographic_source_id TEXT NOT NULL REFERENCES bibliographic_source(id),
  match_method TEXT NOT NULL, PRIMARY KEY (citation_id, bibliographic_source_id, match_method)
);

CREATE VIRTUAL TABLE entry_fts USING fts5(id UNINDEXED, loc_headword, tibetan_headword);
CREATE VIRTUAL TABLE sense_fts USING fts5(id UNINDEXED, entry_id UNINDEXED, definition);
CREATE VIRTUAL TABLE attestation_fts USING fts5(id UNINDEXED, entry_id UNINDEXED, tibetan, german_translation);
CREATE VIRTUAL TABLE citation_fts USING fts5(id UNINDEXED, entry_id UNINDEXED, raw_text, siglum, locator);
CREATE VIRTUAL TABLE bibliography_fts USING fts5(id UNINDEXED, canonical_label, work_title, aliases);

CREATE INDEX sense_entry_idx ON sense(entry_id, ordinal);
CREATE INDEX citation_entry_idx ON citation(entry_id);
CREATE INDEX attestation_entry_idx ON attestation(entry_id);
CREATE INDEX span_source_idx ON record_source_span(snapshot_id, source_id, start_offset);
