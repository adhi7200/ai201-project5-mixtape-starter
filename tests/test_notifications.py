"""
tests/test_notifications.py — Mixtape

Tests for notification creation logic.
"""

import pytest
from app import create_app, db
from models import User, Song
from services.notification_service import rate_song, get_notifications


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def sharer_and_song(app):
    """A song shared by one user, to be rated/added by another."""
    with app.app_context():
        sharer = User(username="aaliya", email="aaliya@example.com")
        other = User(username="kenji", email="kenji@example.com")
        db.session.add_all([sharer, other])
        db.session.flush()

        song = Song(title="Test Song", artist="Test Artist", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()

        yield {"sharer": sharer, "other": other, "song": song}


def test_rating_a_song_notifies_the_sharer(app, sharer_and_song):
    """
    Rating a song you didn't share should notify the original sharer,
    the same way adding it to a playlist does.
    """
    with app.app_context():
        sharer = sharer_and_song["sharer"]
        other = sharer_and_song["other"]
        song = sharer_and_song["song"]

        rate_song(other.id, song.id, 5)

        notifs = get_notifications(sharer.id)
        assert len(notifs) == 1
        assert notifs[0]["type"] == "song_rated"
        assert "kenji" in notifs[0]["body"]


def test_rating_your_own_song_does_not_notify_you(app, sharer_and_song):
    """Rating your own shared song should not create a self-notification."""
    with app.app_context():
        sharer = sharer_and_song["sharer"]
        song = sharer_and_song["song"]

        rate_song(sharer.id, song.id, 4)

        notifs = get_notifications(sharer.id)
        assert notifs == []


def test_re_rating_a_song_notifies_again(app, sharer_and_song):
    """Updating an existing rating should still notify the sharer."""
    with app.app_context():
        sharer = sharer_and_song["sharer"]
        other = sharer_and_song["other"]
        song = sharer_and_song["song"]

        rate_song(other.id, song.id, 3)
        rate_song(other.id, song.id, 5)

        notifs = get_notifications(sharer.id)
        assert len(notifs) == 2

