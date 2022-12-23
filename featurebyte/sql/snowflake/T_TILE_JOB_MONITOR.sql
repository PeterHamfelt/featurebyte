CREATE TABLE TILE_JOB_MONITOR (
  TILE_ID VARCHAR,
  TILE_TYPE VARCHAR,
  SESSION_ID VARCHAR,
  STATUS VARCHAR,
  MESSAGE VARCHAR DEFAULT '',
  CREATED_AT TIMESTAMP DEFAULT SYSDATE()
);