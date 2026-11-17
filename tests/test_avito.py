"""Tests for Avito collector parsing methods."""

import json
import pytest
from src.collectors.avito import AvitoCollector
from src.models.order import SourcePlatform


def test_avito_extract_id():
    collector = AvitoCollector()
    assert collector._extract_id_from_url("https://www.avito.ru/sankt-peterburg/vakansii/operator_chpu_123456789") == "123456789"
    assert collector._extract_id_from_url("https://www.avito.ru/item/987654321?param=1") == "987654321"


def test_avito_parse_ssr_loader_data():
    collector = AvitoCollector()

    sample_ssr = {
        "loaderData": {
            "data": {
                "catalog": {
                    "items": [
                        {
                            "id": 11223344,
                            "title": "Оператор фрезерного станка ЧПУ",
                            "urlPath": "/sankt-peterburg/vakansii/operator_chpu_11223344",
                            "priceDetailed": {
                                "value": 90000,
                                "string": "90 000 ₽",
                            },
                            "location": {
                                "name": "Санкт-Петербург",
                            },
                        },
                        {
                            "id": 55667788,
                            "title": "Сервисный техник постаматов",
                            "urlPath": "/sankt-peterburg/vakansii/tehnik_postamatov_55667788",
                            "priceDetailed": {
                                "value": 0,
                                "string": "75 000 ₽ в месяц",
                            },
                            "location": {
                                "name": "Санкт-Петербург, Московская",
                            },
                        },
                    ]
                }
            }
        }
    }

    html = f"""
    <html>
      <head><title>Вакансии</title></head>
      <body>
        <script>window.something = 1;</script>
        <script>{json.dumps(sample_ssr)}</script>
      </body>
    </html>
    """

    orders = collector._parse_html_listings(html, "https://www.avito.ru/sankt-peterburg/vakansii")
    assert len(orders) == 2

    assert orders[0].source == SourcePlatform.AVITO
    assert orders[0].external_id == "11223344"
    assert orders[0].title == "Оператор фрезерного станка ЧПУ"
    assert orders[0].price == 90000.0
    assert "avito" in orders[0].tags
    assert "Санкт-Петербург" in orders[0].tags

    assert orders[1].source == SourcePlatform.AVITO
    assert orders[1].external_id == "55667788"
    assert orders[1].price == 75000.0
