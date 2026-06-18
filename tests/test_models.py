from models import Artikel, Buchung, Mitglied, User


def test_user_password_hashing(db):
    user = User(username="testuser")
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()

    assert user.check_password("secret123")
    assert not user.check_password("wrongpassword")
    assert "testuser" in repr(user)


def test_mitglied_defaults(db):
    m = Mitglied(name="Max Mustermann", guthaben=500)
    db.session.add(m)
    db.session.commit()

    assert m.id is not None
    assert m.guthaben == 500
    assert m.aktiv is True
    assert m.blacklist is False
    assert m.gepinnt is False
    assert "Max Mustermann" in repr(m)


def test_artikel_defaults(db):
    a = Artikel(name="Bier 0,5L", preis=200)
    db.session.add(a)
    db.session.commit()

    assert a.id is not None
    assert a.aktiv is True
    assert a.preis == 200
    assert "Bier 0,5L" in repr(a)


def test_buchung_links_mitglied_and_artikel(db):
    m = Mitglied(name="Buchung Tester", guthaben=1000)
    a = Artikel(name="Wasser", preis=100)
    db.session.add_all([m, a])
    db.session.commit()

    b = Buchung(
        mitglied_id=m.id,
        artikel_id=a.id,
        menge=2,
        preis_pro_einheit=100,
        gesamtpreis=200,
    )
    db.session.add(b)
    db.session.commit()

    assert b.id is not None
    assert b.storno is False
    assert b.mitglied_obj == m
    assert b.artikel_obj == a
    assert b.gesamtpreis == b.menge * b.preis_pro_einheit
