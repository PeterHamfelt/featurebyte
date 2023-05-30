CREATE TABLE "__TEMP_646f1b781d1e7970788b32ec_2" AS
WITH "REQUEST_TABLE_W7776000_F3600_BS900_M1800_CUSTOMER_ID" AS (
  SELECT
    "POINT_IN_TIME",
    "CUSTOMER_ID",
    FLOOR((
      DATE_PART(EPOCH_SECOND, "POINT_IN_TIME") - 1800
    ) / 3600) AS "__FB_LAST_TILE_INDEX",
    FLOOR((
      DATE_PART(EPOCH_SECOND, "POINT_IN_TIME") - 1800
    ) / 3600) - 2160 AS "__FB_FIRST_TILE_INDEX"
  FROM (
    SELECT DISTINCT
      "POINT_IN_TIME",
      "CUSTOMER_ID"
    FROM REQUEST_TABLE
  )
), _FB_AGGREGATED AS (
  SELECT
    REQ."__FB_ROW_INDEX_FOR_JOIN" AS "__FB_ROW_INDEX_FOR_JOIN",
    REQ."POINT_IN_TIME" AS "POINT_IN_TIME",
    REQ."CUSTOMER_ID" AS "CUSTOMER_ID",
    REQ."_fb_internal_latest_3b3c2a8389d7720826731fefb7060b6578050e04" AS "_fb_internal_latest_3b3c2a8389d7720826731fefb7060b6578050e04",
    "T0"."_fb_internal_window_w7776000_latest_2a1145d57c972a1eace23efb905e5f1e25ba5e73" AS "_fb_internal_window_w7776000_latest_2a1145d57c972a1eace23efb905e5f1e25ba5e73"
  FROM (
    SELECT
      L."__FB_ROW_INDEX_FOR_JOIN" AS "__FB_ROW_INDEX_FOR_JOIN",
      L."POINT_IN_TIME" AS "POINT_IN_TIME",
      L."CUSTOMER_ID" AS "CUSTOMER_ID",
      R.value_latest_3b3c2a8389d7720826731fefb7060b6578050e04 AS "_fb_internal_latest_3b3c2a8389d7720826731fefb7060b6578050e04"
    FROM (
      SELECT
        "__FB_KEY_COL_0",
        "__FB_KEY_COL_1",
        "__FB_LAST_TS",
        "__FB_ROW_INDEX_FOR_JOIN",
        "POINT_IN_TIME",
        "CUSTOMER_ID"
      FROM (
        SELECT
          "__FB_KEY_COL_0",
          "__FB_KEY_COL_1",
          LAG("__FB_EFFECTIVE_TS_COL") IGNORE NULLS OVER (PARTITION BY "__FB_KEY_COL_0", "__FB_KEY_COL_1" ORDER BY "__FB_TS_COL", "__FB_TS_TIE_BREAKER_COL") AS "__FB_LAST_TS",
          "__FB_ROW_INDEX_FOR_JOIN",
          "POINT_IN_TIME",
          "CUSTOMER_ID",
          "__FB_EFFECTIVE_TS_COL"
        FROM (
          SELECT
            FLOOR((
              DATE_PART(EPOCH_SECOND, "POINT_IN_TIME") - 1800
            ) / 3600) AS "__FB_TS_COL",
            "CUSTOMER_ID" AS "__FB_KEY_COL_0",
            "BUSINESS_ID" AS "__FB_KEY_COL_1",
            NULL AS "__FB_EFFECTIVE_TS_COL",
            0 AS "__FB_TS_TIE_BREAKER_COL",
            "__FB_ROW_INDEX_FOR_JOIN" AS "__FB_ROW_INDEX_FOR_JOIN",
            "POINT_IN_TIME" AS "POINT_IN_TIME",
            "CUSTOMER_ID" AS "CUSTOMER_ID"
          FROM (
            SELECT
              REQ."__FB_ROW_INDEX_FOR_JOIN",
              REQ."POINT_IN_TIME",
              REQ."CUSTOMER_ID"
            FROM REQUEST_TABLE AS REQ
          )
          UNION ALL
          SELECT
            "INDEX" AS "__FB_TS_COL",
            "cust_id" AS "__FB_KEY_COL_0",
            "biz_id" AS "__FB_KEY_COL_1",
            "INDEX" AS "__FB_EFFECTIVE_TS_COL",
            1 AS "__FB_TS_TIE_BREAKER_COL",
            NULL AS "__FB_ROW_INDEX_FOR_JOIN",
            NULL AS "POINT_IN_TIME",
            NULL AS "CUSTOMER_ID"
          FROM TILE_F3600_M1800_B900_AF1FD0AEE34EC80A96A6D5A486CE40F5A2267B4E
        )
      )
      WHERE
        "__FB_EFFECTIVE_TS_COL" IS NULL
    ) AS L
    LEFT JOIN TILE_F3600_M1800_B900_AF1FD0AEE34EC80A96A6D5A486CE40F5A2267B4E AS R
      ON L."__FB_LAST_TS" = R."INDEX"
      AND L."__FB_KEY_COL_0" = R."cust_id"
      AND L."__FB_KEY_COL_1" = R."biz_id"
  ) AS REQ
  LEFT JOIN (
    SELECT
      *
    FROM (
      SELECT
        "POINT_IN_TIME",
        "CUSTOMER_ID",
        ROW_NUMBER() OVER (PARTITION BY "POINT_IN_TIME", "CUSTOMER_ID" ORDER BY INDEX DESC NULLS LAST) AS "__FB_ROW_NUMBER",
        FIRST_VALUE(value_latest_2a1145d57c972a1eace23efb905e5f1e25ba5e73) OVER (PARTITION BY "POINT_IN_TIME", "CUSTOMER_ID" ORDER BY INDEX DESC NULLS LAST) AS "_fb_internal_window_w7776000_latest_2a1145d57c972a1eace23efb905e5f1e25ba5e73"
      FROM (
        SELECT
          REQ."POINT_IN_TIME",
          REQ."CUSTOMER_ID",
          TILE.INDEX,
          TILE.value_latest_2a1145d57c972a1eace23efb905e5f1e25ba5e73
        FROM "REQUEST_TABLE_W7776000_F3600_BS900_M1800_CUSTOMER_ID" AS REQ
        INNER JOIN TILE_F3600_M1800_B900_8502F6BC497F17F84385ABE4346FD392F2F56725 AS TILE
          ON FLOOR(REQ.__FB_LAST_TILE_INDEX / 2160) = FLOOR(TILE.INDEX / 2160)
          AND REQ."CUSTOMER_ID" = TILE."cust_id"
        WHERE
          TILE.INDEX >= REQ.__FB_FIRST_TILE_INDEX AND TILE.INDEX < REQ.__FB_LAST_TILE_INDEX
        UNION ALL
        SELECT
          REQ."POINT_IN_TIME",
          REQ."CUSTOMER_ID",
          TILE.INDEX,
          TILE.value_latest_2a1145d57c972a1eace23efb905e5f1e25ba5e73
        FROM "REQUEST_TABLE_W7776000_F3600_BS900_M1800_CUSTOMER_ID" AS REQ
        INNER JOIN TILE_F3600_M1800_B900_8502F6BC497F17F84385ABE4346FD392F2F56725 AS TILE
          ON FLOOR(REQ.__FB_LAST_TILE_INDEX / 2160) - 1 = FLOOR(TILE.INDEX / 2160)
          AND REQ."CUSTOMER_ID" = TILE."cust_id"
        WHERE
          TILE.INDEX >= REQ.__FB_FIRST_TILE_INDEX AND TILE.INDEX < REQ.__FB_LAST_TILE_INDEX
      )
    )
    WHERE
      "__FB_ROW_NUMBER" = 1
  ) AS T0
    ON REQ."POINT_IN_TIME" = T0."POINT_IN_TIME" AND REQ."CUSTOMER_ID" = T0."CUSTOMER_ID"
)
SELECT
  AGG."__FB_ROW_INDEX_FOR_JOIN",
  AGG."POINT_IN_TIME",
  AGG."CUSTOMER_ID",
  "_fb_internal_window_w7776000_latest_2a1145d57c972a1eace23efb905e5f1e25ba5e73" AS "a_latest_value_past_90d",
  "_fb_internal_latest_3b3c2a8389d7720826731fefb7060b6578050e04" AS "a_latest_value"
FROM _FB_AGGREGATED AS AGG