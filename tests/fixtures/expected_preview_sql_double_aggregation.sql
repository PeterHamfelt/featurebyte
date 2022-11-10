WITH fake_transactions_table_f3600_m1800_b900_fa69ec6e12d9162469e8796a5d93c8a1e767dc0d AS (
    SELECT
      avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4.INDEX,
      avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4."cust_id",
      sum_value_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4,
      count_value_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4
    FROM (
        SELECT
          *,
          F_TIMESTAMP_TO_INDEX(__FB_TILE_START_DATE_COLUMN, 1800, 900, 60) AS "INDEX"
        FROM (
            SELECT
              TO_TIMESTAMP(DATE_PART(EPOCH_SECOND, CAST('2022-03-21 09:15:00' AS TIMESTAMP)) + tile_index * 3600) AS __FB_TILE_START_DATE_COLUMN,
              "cust_id",
              SUM("order_size") AS sum_value_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4,
              COUNT("order_size") AS count_value_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4
            FROM (
                SELECT
                  *,
                  FLOOR((DATE_PART(EPOCH_SECOND, "ts") - DATE_PART(EPOCH_SECOND, CAST('2022-03-21 09:15:00' AS TIMESTAMP))) / 3600) AS tile_index
                FROM (
                    SELECT
                      L."ts" AS "ts",
                      L."cust_id" AS "cust_id",
                      L."order_id" AS "order_id",
                      L."order_method" AS "order_method",
                      R."order_size" AS "order_size"
                    FROM (
                        SELECT
                          *
                        FROM (
                            SELECT
                              "ts" AS "ts",
                              "cust_id" AS "cust_id",
                              "order_id" AS "order_id",
                              "order_method" AS "order_method"
                            FROM "db"."public"."event_table"
                        )
                        WHERE
                          "ts" >= CAST('2022-03-21 09:15:00' AS TIMESTAMP)
                          AND "ts" < CAST('2022-04-20 09:15:00' AS TIMESTAMP)
                    ) AS L
                    LEFT JOIN (
                        SELECT
                          "order_id",
                          COUNT(*) AS "order_size"
                        FROM (
                            SELECT
                              "order_id" AS "order_id",
                              "item_id" AS "item_id",
                              "item_name" AS "item_name",
                              "item_type" AS "item_type"
                            FROM "db"."public"."item_table"
                        )
                        GROUP BY
                          "order_id"
                    ) AS R
                      ON L."order_id" = R."order_id"
                )
            )
            GROUP BY
              tile_index,
              "cust_id"
            ORDER BY
              tile_index
        )
    ) AS avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4
), REQUEST_TABLE AS (
    SELECT
      CAST('2022-04-20 10:00:00' AS TIMESTAMP) AS "POINT_IN_TIME",
      'C1' AS "CUSTOMER_ID"
), "REQUEST_TABLE_W2592000_F3600_BS900_M1800_CUSTOMER_ID" AS (
    SELECT
      POINT_IN_TIME,
      "CUSTOMER_ID",
      FLOOR((DATE_PART(EPOCH_SECOND, POINT_IN_TIME) - 1800) / 3600) AS "__FB_LAST_TILE_INDEX",
      FLOOR((DATE_PART(EPOCH_SECOND, POINT_IN_TIME) - 1800) / 3600) - 720 AS "__FB_FIRST_TILE_INDEX"
    FROM (
        SELECT DISTINCT
          POINT_IN_TIME,
          "CUSTOMER_ID"
        FROM REQUEST_TABLE
    )
), _FB_AGGREGATED AS (
    SELECT
      REQ."POINT_IN_TIME",
      REQ."CUSTOMER_ID",
      "T0"."agg_w2592000_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4" AS "agg_w2592000_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4"
    FROM REQUEST_TABLE AS REQ
    LEFT JOIN (
        SELECT
          REQ.POINT_IN_TIME,
          REQ."CUSTOMER_ID",
          SUM(sum_value_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4) / SUM(count_value_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4) AS "agg_w2592000_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4"
        FROM "REQUEST_TABLE_W2592000_F3600_BS900_M1800_CUSTOMER_ID" AS REQ
        INNER JOIN fake_transactions_table_f3600_m1800_b900_fa69ec6e12d9162469e8796a5d93c8a1e767dc0d AS TILE
          ON (FLOOR(REQ.__FB_LAST_TILE_INDEX / 720) = FLOOR(TILE.INDEX / 720) OR FLOOR(REQ.__FB_LAST_TILE_INDEX / 720) - 1 = FLOOR(TILE.INDEX / 720))
          AND REQ."CUSTOMER_ID" = TILE."cust_id"
        WHERE
          TILE.INDEX >= REQ.__FB_FIRST_TILE_INDEX
          AND TILE.INDEX < REQ.__FB_LAST_TILE_INDEX
        GROUP BY
          REQ.POINT_IN_TIME,
          REQ."CUSTOMER_ID"
    ) AS T0
      ON REQ.POINT_IN_TIME = T0.POINT_IN_TIME
      AND REQ."CUSTOMER_ID" = T0."CUSTOMER_ID"
)
SELECT
  AGG."POINT_IN_TIME",
  AGG."CUSTOMER_ID",
  "agg_w2592000_avg_bcad6431925d36df57c6afd2b2c46b1a1f5110d4" AS "order_size_30d_avg"
FROM _FB_AGGREGATED AS AGG