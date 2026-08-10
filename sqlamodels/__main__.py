from __future__ import annotations

from . import mysql_ui, schema_ui
from .cli import cli

__all__ = ["cli", "mysql_ui", "schema_ui"]

if __name__ == "__main__":
    cli()
