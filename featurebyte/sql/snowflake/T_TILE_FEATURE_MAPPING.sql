CREATE TABLE TILE_FEATURE_MAPPING (
  TILE_ID VARCHAR,
  FEATURE_NAME VARCHAR,
  FEATURE_VERSION VARCHAR,
  FEATURE_READINESS VARCHAR,
  FEATURE_TABULAR_DATA_IDS VARCHAR,
  FEATURE_SQL VARCHAR,
  FEATURE_STORE_TABLE_NAME VARCHAR,
  FEATURE_ENTITY_COLUMN_NAMES VARCHAR,
  IS_DELETED BOOLEAN DEFAULT FALSE,
  CREATED_AT TIMESTAMP DEFAULT SYSDATE()
);
