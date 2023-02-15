CREATE TABLE IF NOT EXISTS TILE_JOB_MONITOR (
  TILE_ID STRING,
  AGGREGATION_ID STRING,
  TILE_TYPE STRING,
  SESSION_ID STRING,
  STATUS STRING,
  MESSAGE STRING,
  CREATED_AT TIMESTAMP
) USING delta;
