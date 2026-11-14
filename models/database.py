"""SQLite helpers: connections, schema initialisation, small query utilities."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click
from flask import current_app, g

from .schema import SCHEMA


def connect(path):
    """Open a connection with row access by name and foreign keys enforced."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path):
    """Create all tables (safe to call repeatedly)."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def query_one(db, sql, args=()):
    return db.execute(sql, args).fetchone()


def query_all(db, sql, args=()):
    return db.execute(sql, args).fetchall()


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def loads(value, default=None):
    if value in (None, ""):
        return [] if default is None else default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return [] if default is None else default


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@click.command("init-db")
def init_db_command():
    """flask --app app init-db : create the SQLite database and tables."""
    init_db(current_app.config["DATABASE"])
    click.echo("Database initialised at " + current_app.config["DATABASE"])


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
