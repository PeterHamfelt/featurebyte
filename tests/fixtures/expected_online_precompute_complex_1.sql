SELECT
  "BUSINESS_ID",
  '_fb_internal_window_w604800_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8' AS "AGGREGATION_RESULT_NAME",
  "_fb_internal_window_w604800_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8" AS "VALUE"
FROM (
  WITH REQUEST_TABLE AS (
    SELECT DISTINCT
      CAST(__FB_POINT_IN_TIME_SQL_PLACEHOLDER AS TIMESTAMPNTZ) AS POINT_IN_TIME,
      "biz_id" AS "BUSINESS_ID"
    FROM TILE_F3600_M1800_B900_7BD30FF1B8E84ADD2B289714C473F1A21E9BC624
    WHERE
      INDEX >= FLOOR(
        (
          DATE_PART(EPOCH_SECOND, CAST(__FB_POINT_IN_TIME_SQL_PLACEHOLDER AS TIMESTAMPNTZ)) - 1800
        ) / 3600
      ) - 168
      AND INDEX < FLOOR(
        (
          DATE_PART(EPOCH_SECOND, CAST(__FB_POINT_IN_TIME_SQL_PLACEHOLDER AS TIMESTAMPNTZ)) - 1800
        ) / 3600
      )
  ), "REQUEST_TABLE_W604800_F3600_BS900_M1800_BUSINESS_ID" AS (
    SELECT
      "POINT_IN_TIME",
      "BUSINESS_ID",
      FLOOR((
        DATE_PART(EPOCH_SECOND, "POINT_IN_TIME") - 1800
      ) / 3600) AS "__FB_LAST_TILE_INDEX",
      FLOOR((
        DATE_PART(EPOCH_SECOND, "POINT_IN_TIME") - 1800
      ) / 3600) - 168 AS "__FB_FIRST_TILE_INDEX"
    FROM (
      SELECT DISTINCT
        "POINT_IN_TIME",
        "BUSINESS_ID"
      FROM REQUEST_TABLE
    )
  ), _FB_AGGREGATED AS (
    SELECT
      REQ."POINT_IN_TIME",
      REQ."BUSINESS_ID",
      "T0"."_fb_internal_window_w604800_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8" AS "_fb_internal_window_w604800_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8"
    FROM REQUEST_TABLE AS REQ
    LEFT JOIN (
      SELECT
        "POINT_IN_TIME",
        "BUSINESS_ID",
        SUM(value_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8) AS "_fb_internal_window_w604800_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8"
      FROM (
        SELECT
          REQ."POINT_IN_TIME",
          REQ."BUSINESS_ID",
          TILE.INDEX,
          TILE.value_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8
        FROM "REQUEST_TABLE_W604800_F3600_BS900_M1800_BUSINESS_ID" AS REQ
        INNER JOIN TILE_F3600_M1800_B900_7BD30FF1B8E84ADD2B289714C473F1A21E9BC624 AS TILE
          ON FLOOR(REQ.__FB_LAST_TILE_INDEX / 168) = FLOOR(TILE.INDEX / 168)
          AND REQ."BUSINESS_ID" = TILE."biz_id"
        WHERE
          TILE.INDEX >= REQ.__FB_FIRST_TILE_INDEX AND TILE.INDEX < REQ.__FB_LAST_TILE_INDEX
        UNION ALL
        SELECT
          REQ."POINT_IN_TIME",
          REQ."BUSINESS_ID",
          TILE.INDEX,
          TILE.value_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8
        FROM "REQUEST_TABLE_W604800_F3600_BS900_M1800_BUSINESS_ID" AS REQ
        INNER JOIN TILE_F3600_M1800_B900_7BD30FF1B8E84ADD2B289714C473F1A21E9BC624 AS TILE
          ON FLOOR(REQ.__FB_LAST_TILE_INDEX / 168) - 1 = FLOOR(TILE.INDEX / 168)
          AND REQ."BUSINESS_ID" = TILE."biz_id"
        WHERE
          TILE.INDEX >= REQ.__FB_FIRST_TILE_INDEX AND TILE.INDEX < REQ.__FB_LAST_TILE_INDEX
      )
      GROUP BY
        "POINT_IN_TIME",
        "BUSINESS_ID"
    ) AS T0
      ON REQ."POINT_IN_TIME" = T0."POINT_IN_TIME" AND REQ."BUSINESS_ID" = T0."BUSINESS_ID"
  )
  SELECT
    AGG."POINT_IN_TIME",
    AGG."BUSINESS_ID",
    "_fb_internal_window_w604800_sum_ea3e51f28222785a9bc856e4f09a8ce4642bc6c8"
  FROM _FB_AGGREGATED AS AGG
)
