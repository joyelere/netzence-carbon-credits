"""Write openapi.yml from the app's routes: python scripts/export_openapi.py"""

import yaml

from app.main import app


def render() -> str:
    return yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    with open("openapi.yml", "w") as f:
        f.write(render())
    print("openapi.yml updated")
