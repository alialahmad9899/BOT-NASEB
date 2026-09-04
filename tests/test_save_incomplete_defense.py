from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.admin_models import ProfileAdminMeta
from app.database.models import Base, Profile, ProfileContact
from app.database.repositories import ProfileRepository
from app.services.profiles import ProfileDraft


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _incomplete_draft():
    return ProfileDraft(
        public_data={
            "gender": "female",
            "name": None,
            "age": None,
            "residence": None,
            "marital_status": None,
            "children_count": None,
            "occupation": None,
            "education": None,
            "height": None,
            "weight": None,
            "appearance": None,
            "partner_requirements": None,
            "photo_file_id": None,
        },
        private_contact_data={"phone": None, "telegram_username": None, "whatsapp": None},
    )


def test_repository_can_persist_incomplete_profile():
    engine = _session()
    with Session(engine) as session:
        profile = ProfileRepository(session).create(_incomplete_draft(), request_number=999)
        session.commit()

        saved = session.get(Profile, profile.id)
        assert saved is not None
        assert saved.request_number == 999
        assert saved.gender == "female"
        assert saved.age is None
        assert saved.residence is None
        assert session.get(ProfileContact, profile.id) is not None


def test_incomplete_profile_meta_can_be_created_after_persistence():
    engine = _session()
    with Session(engine) as session:
        profile = ProfileRepository(session).create(_incomplete_draft(), request_number=1000)
        meta = ProfileAdminMeta(profile_id=profile.id, quality_score=30, publication_status="review")
        session.add(meta)
        session.commit()

        saved_meta = session.get(ProfileAdminMeta, profile.id)
        assert saved_meta is not None
        assert saved_meta.publication_status == "review"


def test_request_number_is_not_required_by_repository_create():
    engine = _session()
    with Session(engine) as session:
        profile = ProfileRepository(session).create(_incomplete_draft())
        session.commit()
        assert profile.request_number == 101
