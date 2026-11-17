"""SQLite connections follow worker lifetime without interrupting live workers."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from filemate.execution.storage import SQLiteStorage


def test_retired_worker_connection_is_released_before_replacement(tmp_path):
    storage = SQLiteStorage(tmp_path / 'workers.db')
    storage.init_schema()
    try:
        with ThreadPoolExecutor(max_workers=1) as first:
            retired = first.submit(storage._conn).result()
        with ThreadPoolExecutor(max_workers=1) as second:
            assert second.submit(lambda: storage._conn().execute('SELECT 1').fetchone()[0]).result() == 1
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            retired.execute('SELECT 1')
        assert storage._conn().execute('SELECT 1').fetchone()[0] == 1
    finally:
        storage.close()


def test_live_worker_keeps_connection_during_other_worker_creation(tmp_path):
    storage = SQLiteStorage(tmp_path / 'live.db')
    storage.init_schema()
    started, release = Event(), Event()
    def live_worker():
        connection = storage._conn()
        started.set()
        assert release.wait(5)
        return connection.execute('SELECT 42').fetchone()[0]
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(live_worker)
            assert started.wait(5)
            try:
                assert workers.submit(lambda: storage._conn().execute('SELECT 1').fetchone()[0]).result() == 1
            finally:
                release.set()
            assert first.result() == 42
    finally:
        release.set()
        storage.close()


def test_committed_data_survives_many_worker_retirements(tmp_path):
    storage = SQLiteStorage(tmp_path / 'cycles.db')
    connection = storage._conn()
    connection.execute('CREATE TABLE evidence (id INTEGER PRIMARY KEY)')
    connection.commit()
    retired = []
    def insert(value):
        conn = storage._conn()
        conn.execute('INSERT INTO evidence VALUES (?)', (value,))
        conn.commit()
        return conn
    try:
        for value in range(20):
            with ThreadPoolExecutor(max_workers=1) as workers:
                retired.append(workers.submit(insert, value).result())
        assert storage._conn().execute('SELECT COUNT(*) FROM evidence').fetchone()[0] == 20
        for old in retired[:-1]:
            with pytest.raises(sqlite3.ProgrammingError, match='closed'):
                old.execute('SELECT 1')
        storage.close()
        storage.close()
    finally:
        storage.close()
