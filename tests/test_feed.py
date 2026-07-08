"""
tests/test_feed.py — Mixtape

Tests for the "Friends Listening Now" feed logic.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def nova_and_darius(app):
    """Two friends and a song, ready for a ListeningEvent to be attached."""
    with app.app_context():
        nova = User(username="nova", email="nova@example.com")
        darius = User(username="darius", email="darius@example.com")
        db.session.add_all([nova, darius])
        db.session.flush()

        db.session.execute(friendships.insert().values(user_id=nova.id, friend_id=darius.id))
        db.session.execute(friendships.insert().values(user_id=darius.id, friend_id=nova.id))

        song = Song(title="Test Song", artist="Test Artist", shared_by=nova.id)
        db.session.add(song)
        db.session.commit()

        yield {"nova": nova, "darius": darius, "song": song}


def _freeze_now(dt):
    """Patch feed_service's datetime.now so get_friends_listening_now sees a fixed 'now'."""
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return dt

    return patch("services.feed_service.datetime", FrozenDatetime)


def test_listen_from_yesterday_evening_does_not_appear_this_morning(app, nova_and_darius):
    """
    A friend's listen from 11pm the previous night should not appear in
    "listening now" at 9am the next day, even though it's within a
    24-hour rolling window of the current time.
    """
    with app.app_context():
        nova = nova_and_darius["nova"]
        darius = nova_and_darius["darius"]
        song = nova_and_darius["song"]

        last_night = datetime(2024, 6, 10, 23, 0, 0, tzinfo=timezone.utc)  # Mon 11pm
        this_morning = datetime(2024, 6, 11, 9, 0, 0, tzinfo=timezone.utc)  # Tue 9am (10 hrs later)

        event = ListeningEvent(user_id=darius.id, song_id=song.id, listened_at=last_night)
        db.session.add(event)
        db.session.commit()

        with _freeze_now(this_morning):
            feed = get_friends_listening_now(nova.id)

        assert feed == []


def test_listen_from_earlier_today_appears(app, nova_and_darius):
    """A friend's listen from earlier the same calendar day should appear."""
    with app.app_context():
        nova = nova_and_darius["nova"]
        darius = nova_and_darius["darius"]
        song = nova_and_darius["song"]

        this_morning = datetime(2024, 6, 11, 8, 0, 0, tzinfo=timezone.utc)
        this_afternoon = datetime(2024, 6, 11, 15, 0, 0, tzinfo=timezone.utc)

        event = ListeningEvent(user_id=darius.id, song_id=song.id, listened_at=this_morning)
        db.session.add(event)
        db.session.commit()

        with _freeze_now(this_afternoon):
            feed = get_friends_listening_now(nova.id)

        assert len(feed) == 1
        assert feed[0]["friend"]["username"] == "darius"


def test_no_friends_returns_empty_list(app):
    """A user with no friends gets an empty feed, not an error."""
    with app.app_context():
        solo = User(username="solo", email="solo@example.com")
        db.session.add(solo)
        db.session.commit()

        feed = get_friends_listening_now(solo.id)
        assert feed == []
