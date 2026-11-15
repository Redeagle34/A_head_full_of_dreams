"""Read-only access to data/fire.duckdb."""
import duckdb

from .config import DB_PATH

_connection = None


class Missing(RuntimeError):
    """The database file has not been built yet; the message names the script."""


def cursor():
    """A cursor for one request. Cursors are cheap and safe to use from any thread."""
    global _connection
    if _connection is None:
        if not DB_PATH.exists():
            raise Missing(f"{DB_PATH} is missing. Run: python pipeline/build_db.py")
        _connection = duckdb.connect(str(DB_PATH), read_only=True)
    return _connection.cursor()
