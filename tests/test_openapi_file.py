"""openapi.yml is generated from the code; regenerate it with `make openapi`."""

from scripts.export_openapi import render


def test_openapi_yml_is_up_to_date():
    with open("openapi.yml") as f:
        assert f.read() == render(), "openapi.yml is stale: run `make openapi`"
