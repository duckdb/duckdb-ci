#include "duckdb.h"
#include <stdio.h>

int main(void) {
  duckdb_database db;
  duckdb_connection con;
  duckdb_result result;

  if (duckdb_open(NULL, &db) != DuckDBSuccess) {
    fprintf(stderr, "duckdb_open failed\n");
    return 1;
  }
  if (duckdb_connect(db, &con) != DuckDBSuccess) {
    fprintf(stderr, "duckdb_connect failed\n");
    duckdb_close(&db);
    return 1;
  }
  if (duckdb_query(con, "SELECT 42", &result) != DuckDBSuccess) {
    fprintf(stderr, "duckdb_query failed: %s\n", duckdb_result_error(&result));
    duckdb_disconnect(&con);
    duckdb_close(&db);
    return 1;
  }

  if (duckdb_row_count(&result) != 1 || duckdb_column_count(&result) != 1) {
    fprintf(stderr, "unexpected result shape\n");
    duckdb_destroy_result(&result);
    duckdb_disconnect(&con);
    duckdb_close(&db);
    return 1;
  }

  printf("result=%lld\n", (long long)duckdb_value_int64(&result, 0, 0));
  duckdb_destroy_result(&result);
  duckdb_disconnect(&con);
  duckdb_close(&db);
  return 0;
}
