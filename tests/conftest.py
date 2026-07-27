import io
import pytest
import pandas as pd
from app import create_app
from models import db as _db, User, Mitglied, Artikel


@pytest.fixture()
def app():
    """Fresh app + in-memory SQLite DB per test."""
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def admin_user(db):
    u = User(username="testadmin")
    u.set_password("testpassword")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def auth_client(client, admin_user):
    """Test client with an active admin session."""
    client.post("/login", data={"username": "testadmin", "password": "testpassword"})
    return client


@pytest.fixture()
def mitglied(db):
    m = Mitglied(name="Test Mitglied", guthaben=1000, aktiv=True)
    db.session.add(m)
    db.session.commit()
    return m


@pytest.fixture()
def artikel(db):
    a = Artikel(name="Test Bier", preis=200, reihenfolge=1, aktiv=True)
    db.session.add(a)
    db.session.commit()
    return a


def make_excel(rows: list[dict]) -> io.BytesIO:
    """Helper: build an in-memory Excel file from a list of dicts."""
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    buf.seek(0)
    return buf
