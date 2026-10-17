"""start_scheduler must only run in the process that wins the advisory lock."""
from unittest.mock import MagicMock, patch

import app as app_module


def _pg_engine(got_lock):
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    conn = engine.connect.return_value
    conn.exec_driver_sql.return_value.scalar.return_value = got_lock
    return engine, conn


def test_lock_won_keeps_connection(app):
    engine, conn = _pg_engine(True)
    with patch("models.db", MagicMock(engine=engine)):
        assert app_module._acquire_scheduler_lock(app) is True
    assert app_module._scheduler_lock_conn is conn
    conn.close.assert_not_called()
    app_module._scheduler_lock_conn = None


def test_lock_lost_closes_connection(app):
    engine, conn = _pg_engine(False)
    with patch("models.db", MagicMock(engine=engine)):
        assert app_module._acquire_scheduler_lock(app) is False
    conn.close.assert_called_once()


def test_non_postgres_always_wins(app):
    assert app_module._acquire_scheduler_lock(app) is True  # sqlite in tests


def test_start_scheduler_skipped_when_lock_lost(app):
    app.config["TESTING"] = False
    with patch.object(app_module, "_acquire_scheduler_lock", return_value=False), \
         patch("flask_apscheduler.APScheduler") as sched:
        assert app_module.start_scheduler(app) is None
    sched.assert_not_called()


def test_start_scheduler_runs_when_lock_won(app):
    app.config["TESTING"] = False
    with patch.object(app_module, "_acquire_scheduler_lock", return_value=True), \
         patch("flask_apscheduler.APScheduler") as sched:
        app_module.start_scheduler(app)
    sched.return_value.start.assert_called_once()
