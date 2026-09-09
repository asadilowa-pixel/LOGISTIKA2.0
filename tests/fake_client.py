class FakeQueryResult:
    def __init__(self, column_names, result_rows):
        self.column_names = column_names
        self.result_rows = result_rows


class FakeClient:
    """Stands in for clickhouse_connect's Client in tests: .query(sql) returns
    a preset result regardless of the SQL text, and every call is recorded so
    tests can assert on the table/limit that was actually queried."""

    def __init__(self, result: FakeQueryResult):
        self.result = result
        self.queries: list[str] = []

    def query(self, sql: str):
        self.queries.append(sql)
        return self.result

    def close(self):
        pass
