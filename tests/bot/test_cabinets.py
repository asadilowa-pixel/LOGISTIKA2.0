import pytest

from app.bot.cabinets import load_ozon_cabinets, load_wb_cabinets


def test_load_ozon_cabinets_parses_multiple():
    env = {
        "OZON_CABINET_1_NAME": "Основной",
        "OZON_CABINET_1_CLIENT_ID": "111",
        "OZON_CABINET_1_API_KEY": "key-1",
        "OZON_CABINET_2_NAME": "Второй",
        "OZON_CABINET_2_CLIENT_ID": "222",
        "OZON_CABINET_2_API_KEY": "key-2",
        "UNRELATED_VAR": "ignored",
    }

    cabinets = load_ozon_cabinets(env)

    assert [c.cabinet_id for c in cabinets] == [1, 2]
    assert cabinets[0].name == "Основной"
    assert cabinets[0].client_id == "111"
    assert cabinets[0].api_key == "key-1"


def test_load_ozon_cabinets_missing_field_raises():
    env = {"OZON_CABINET_1_NAME": "Основной", "OZON_CABINET_1_CLIENT_ID": "111"}

    with pytest.raises(ValueError):
        load_ozon_cabinets(env)


def test_load_wb_cabinets_parses_multiple():
    env = {
        "WB_CABINET_5_NAME": "Склад-А",
        "WB_CABINET_5_TOKEN": "tok-5",
    }

    cabinets = load_wb_cabinets(env)

    assert cabinets == [__import__("app.bot.cabinets", fromlist=["WbCabinet"]).WbCabinet(
        cabinet_id=5, name="Склад-А", token="tok-5"
    )]
