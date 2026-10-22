# use SQLite locally and PostgreSQL when DATABASE_URL is set
import os
import sqlite3
from pathlib import Path


def is_postgres():
    return bool(os.getenv('DATABASE_URL', '').strip())


class PgConnection:
    # run the app's queries with PostgreSQL
    def __init__(self):
        import psycopg
        from psycopg.rows import dict_row
        self._conn = psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row,
                                     connect_timeout=10)

    def execute(self, query, params=()):
        # PostgreSQL uses %s for the values instead of ?
        return self._conn.execute(query.replace('?', '%s'), params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


def connect(sqlite_path):
    # choose the database based on the environment settings
    if is_postgres():
        return PgConnection()
    c = sqlite3.connect(sqlite_path)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def insert_id(c, sql, params):
    # return the ID of the record we just added
    if is_postgres():
        return c.execute(sql + ' RETURNING id', params).fetchone()['id']
    return c.execute(sql, params).lastrowid


def init_postgres():
    # create the tables and any missing columns
    statements = [
        '''CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            phone TEXT, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'party',
            created_at TEXT DEFAULT (timezone('UTC', now())::text),
            national_id TEXT, birth_date TEXT,
            notification_status INTEGER DEFAULT 1, notification_result INTEGER DEFAULT 1)''',
        '''CREATE TABLE IF NOT EXISTS cases(
            id SERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
            creator_id INTEGER NOT NULL REFERENCES users(id), accident_type TEXT NOT NULL,
            accident_date TEXT NOT NULL, accident_time TEXT NOT NULL, location TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_second_party',
            created_at TEXT DEFAULT (timezone('UTC', now())::text))''',
        '''CREATE TABLE IF NOT EXISTS parties(
            id SERIAL PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id), position TEXT NOT NULL CHECK(position IN ('A','B')),
            full_name TEXT, national_id TEXT, phone TEXT, description TEXT,
            completed INTEGER NOT NULL DEFAULT 0, UNIQUE(case_id,position))''',
        '''CREATE TABLE IF NOT EXISTS vehicles(
            id SERIAL PRIMARY KEY, party_id INTEGER NOT NULL UNIQUE REFERENCES parties(id) ON DELETE CASCADE,
            plate TEXT, manufacturer TEXT, model TEXT, year INTEGER, color TEXT)''',
        '''CREATE TABLE IF NOT EXISTS invitations(
            id SERIAL PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL,
            claimed_by INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT (timezone('UTC', now())::text),
            recipient_email TEXT, recipient_phone TEXT, revoked_at TEXT)''',
        '''CREATE TABLE IF NOT EXISTS videos(
            id SERIAL PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            party_id INTEGER NOT NULL REFERENCES parties(id), original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL, processed_name TEXT,
            privacy_status TEXT NOT NULL DEFAULT 'pending',
            uploaded_at TEXT DEFAULT (timezone('UTC', now())::text), processing_note TEXT)''',
        '''CREATE TABLE IF NOT EXISTS garage_vehicles(
            id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plate TEXT NOT NULL, manufacturer TEXT NOT NULL, model TEXT NOT NULL,
            year INTEGER NOT NULL, color TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS analysis_jobs(
            id SERIAL PRIMARY KEY, video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'not_started', details TEXT,
            updated_at TEXT DEFAULT (timezone('UTC', now())::text))''',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS national_id TEXT',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date TEXT',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_status INTEGER DEFAULT 1',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_result INTEGER DEFAULT 1',
        'CREATE UNIQUE INDEX IF NOT EXISTS users_national_id_unique ON users(national_id)',
        'ALTER TABLE invitations ADD COLUMN IF NOT EXISTS recipient_email TEXT',
        'ALTER TABLE invitations ADD COLUMN IF NOT EXISTS recipient_phone TEXT',
        'ALTER TABLE invitations ADD COLUMN IF NOT EXISTS revoked_at TEXT',
    ]
    with PgConnection() as c:
        for statement in statements:
            c.execute(statement)
