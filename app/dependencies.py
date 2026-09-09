from clickhouse_connect.driver.client import Client
from fastapi import Request


def get_ch_client(request: Request) -> Client:
    return request.app.state.ch_client
