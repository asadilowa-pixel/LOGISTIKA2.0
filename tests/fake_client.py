class FakeQueryResult:
    def __init__(self, column_names, result_rows):
        self.column_names = column_names
        self.result_rows = result_rows


class FakeClient:
    """Stands in for clickhouse_connect's Client in tests. Every call is
    recorded so tests can assert on the table/limit that was actually
    queried. `result` is either a single FakeQueryResult returned for every
    call, or a dict of {table-name-substring: FakeQueryResult} for callers
    (like fetch_unified_stocks) that query more than one table."""

    def __init__(self, result):
        self.result = result
        self.queries: list[str] = []
        self.query_params: list[dict | None] = []

    def query(self, sql: str, parameters: dict | None = None):
        self.queries.append(sql)
        self.query_params.append(parameters)
        if isinstance(self.result, dict):
            for key, value in self.result.items():
                if key in sql:
                    return value
            raise KeyError(f"no fake result configured for query: {sql}")
        return self.result

    def close(self):
        pass
