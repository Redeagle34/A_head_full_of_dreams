"""Read-only access to data/fire.duckdb, and a connection for reading the Parquet files."""
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


_files = None


def files():
    """A cursor for queries on Parquet files (data/events/). One connection for the whole server:
    opening a new one costs about 30 ms, more than most of these queries."""
    global _files
    if _files is None:
        _files = duckdb.connect()
    return _files.cursor()
