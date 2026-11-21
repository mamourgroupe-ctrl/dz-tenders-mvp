import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

class DummyCursor:
    def __init__(self, cur):
        self.cur = cur
    def execute(self, query, params=None):
        if params:
            query = query.replace("?", "%s")
        self.cur.execute(query, params)
        return self
    def fetchone(self):
        return self.cur.fetchone()
    def fetchall(self):
        return self.cur.fetchall()
    def __iter__(self):
        return iter(self.cur)
    @property
    def rowcount(self):
        return self.cur.rowcount

class PostgresConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn
        self.cur = DummyCursor(conn.cursor(cursor_factory=RealDictCursor))
    def execute(self, query, params=None):
        self.cur.execute(query, params)
        return self.cur
    def executescript(self, script):
        self.cur.execute(script)
    def commit(self):
        self.conn.commit()
    def close(self):
        self.conn.close()
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()

def get_db_connection(uri_or_path=None, uri=False):
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        if "sslmode" not in db_url:
            db_url += "?sslmode=require" if "?" not in db_url else "&sslmode=require"
        conn = psycopg2.connect(db_url)
        return PostgresConnectionWrapper(conn)
    else:
        if not uri_or_path:
            uri_or_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "tenders.db")
        if uri:
            conn = sqlite3.connect(uri_or_path, uri=True)
        else:
            conn = sqlite3.connect(uri_or_path)
        conn.row_factory = sqlite3.Row
        return conn
