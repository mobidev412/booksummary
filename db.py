import psycopg2
import psycopg2.extras
import psycopg2.pool
import os
import threading

DATABASE_URL = os.environ.get("DATABASE_URL")

# ─────────────────────────────────────────────────────────────────────────────
# Connection Pool
# Reuses existing connections instead of opening a new one on every DB call.
# Saves ~50–150ms per request that was previously wasted on TCP handshakes.
# ThreadedConnectionPool is safe for Flask's multi-threaded dev server.
# ─────────────────────────────────────────────────────────────────────────────

_pool      = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:           # double-checked locking
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=10,
                    dsn=DATABASE_URL,
                )
                print("[db] ✅ Connection pool created (min=2, max=10)")
    return _pool


class _PooledConn:
    """
    Transparent wrapper around a pooled connection.
    Calling .close() returns the connection to the pool instead of destroying it,
    so all existing code (cache.py, preferences.py, user.py, etc.) works unchanged.
    """
    __slots__ = ("_conn", "_pool")

    def __init__(self, conn, pool):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_pool", pool)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_conn"), name, value)

    def close(self):
        pool = object.__getattribute__(self, "_pool")
        conn = object.__getattribute__(self, "_conn")
        try:
            if not conn.closed:
                conn.reset()        # rollback any uncommitted txn before reuse
        except Exception:
            pass
        pool.putconn(conn)


def get_connection():
    pool = _get_pool()
    conn = pool.getconn()
    return _PooledConn(conn, pool)


def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def test_connection():
    try:
        conn   = get_connection()
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables   = {row["table_name"] for row in cursor.fetchall()}
        required = {"users", "user_preferences", "books", "summaries", "chat_history"}
        missing  = required - tables
        conn.close()

        if missing:
            print(f"  Missing tables: {missing}")
            print("   Please create them in your Notebook first.")
            return False

        print(" Database connection successful.")
        print(f"   Tables found: {', '.join(sorted(tables))}")
        return True

    except Exception as e:
        print(f" Database connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()