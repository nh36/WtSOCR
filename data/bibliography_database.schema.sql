-- Separate, source-scoped authority sidecar. No modification of lexical candidates.
PRAGMA foreign_keys = ON;
CREATE TABLE authority (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('work','publication','abbreviation')),
  label TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE occurrence (
  id TEXT PRIMARY KEY, authority_id TEXT NOT NULL REFERENCES authority(id),
  source_sha256 TEXT NOT NULL, source_url TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE relation (
  occurrence_id TEXT NOT NULL REFERENCES occurrence(id), ordinal INTEGER NOT NULL CHECK(ordinal>0),
  work_id TEXT NOT NULL REFERENCES authority(id), status TEXT NOT NULL, record_json TEXT NOT NULL,
  PRIMARY KEY(occurrence_id,ordinal)
);
CREATE TABLE print_occurrence (
  id TEXT PRIMARY KEY, authority_id TEXT NOT NULL REFERENCES authority(id),
  online_occurrence_id TEXT REFERENCES occurrence(id),
  pdf_sha256 TEXT NOT NULL, ocr_sha256 TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE publication_relation (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES authority(id),
  target_id TEXT NOT NULL REFERENCES authority(id),
  relation_type TEXT NOT NULL CHECK(relation_type IN ('different_edition','reprint_of','possible_same_work')),
  status TEXT NOT NULL CHECK(status IN ('candidate','reviewed')),
  record_json TEXT NOT NULL, CHECK(source_id<>target_id)
);
CREATE TABLE relation_candidate (
  occurrence_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
  publication_id TEXT NOT NULL REFERENCES authority(id),
  PRIMARY KEY(occurrence_id,ordinal,publication_id),
  FOREIGN KEY(occurrence_id,ordinal) REFERENCES relation(occurrence_id,ordinal)
);
CREATE TABLE citation_resolution (
  layer TEXT NOT NULL CHECK(layer IN ('html','pdf')), citation_id TEXT NOT NULL,
  status TEXT NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(layer,citation_id)
);
CREATE TABLE citation_target (
  layer TEXT NOT NULL, citation_id TEXT NOT NULL, component_ordinal INTEGER NOT NULL CHECK(component_ordinal>0),
  authority_id TEXT NOT NULL REFERENCES authority(id), start INTEGER NOT NULL CHECK(start>=0),
  end INTEGER NOT NULL CHECK(end>start),
  target_status TEXT NOT NULL CHECK(target_status IN ('accepted_identity','candidate')),
  PRIMARY KEY(layer,citation_id,component_ordinal,authority_id),
  FOREIGN KEY(layer,citation_id) REFERENCES citation_resolution(layer,citation_id)
);
CREATE VIEW accepted_citation_target AS SELECT * FROM citation_target WHERE target_status='accepted_identity';
CREATE INDEX citation_target_authority ON citation_target(authority_id,target_status);
