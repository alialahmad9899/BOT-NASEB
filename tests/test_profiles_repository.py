from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.database.repositories import ProfileFilters, ProfileRepository
from app.services.profiles import ProfileDraft


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_profile_assigns_unique_request_number_and_separates_contact():
    with make_session() as session:
        repo = ProfileRepository(session)
        profile = repo.create(
            ProfileDraft(
                public_data={
                    "gender": "female", "name": "آية", "age": 24, "province": "ريف دمشق",
                    "city": "جرمانا", "marital_status": "عزباء", "occupation": "مدرسة",
                    "height": 165, "weight": None, "description": "هادية ومحترمة",
                    "partner_requirements": "شاب محترم", "photo_file_id": None,
                },
                private_contact_data={
                    "phone": "0900000000", "telegram_username": "aya24", "whatsapp": "0900000000",
                },
            )
        )
        assert profile.request_number is not None
        assert repo.get_contact(profile.request_number).phone == "0900000000"
        public = repo.get_public(profile.request_number)
        assert public["name"] == "آية"
        assert "phone" not in public


def test_search_applies_multiple_database_filters():
    with make_session() as session:
        repo = ProfileRepository(session)
        for age, city in [(24, "جرمانا"), (29, "دمشق"), (25, "جرمانا")]:
            repo.create(
                ProfileDraft(
                    public_data={
                        "gender": "female", "name": f"بنت {age}", "age": age,
                        "province": "ريف دمشق" if city == "جرمانا" else "دمشق", "city": city,
                        "marital_status": "عزباء", "occupation": "مدرسة", "height": None,
                        "weight": None, "description": "", "partner_requirements": "", "photo_file_id": None,
                    },
                    private_contact_data={"phone": f"09{age}000000"},
                )
            )
        session.commit()
        rows = repo.search(ProfileFilters(province="ريف دمشق", age_min=24, age_max=25))
        assert [row.age for row in rows] == [24, 25]


def test_public_repository_view_never_exposes_contact_record():
    with make_session() as session:
        repo = ProfileRepository(session)
        profile = repo.create(
            ProfileDraft(
                public_data={"gender": "female", "name": "سارة", "age": 25, "province": "دمشق"},
                private_contact_data={"phone": "0911223344", "telegram_username": "sara25"},
            )
        )
        session.commit()
        public = repo.get_public(profile.request_number)
        assert public is not None
        assert public["name"] == "سارة"
        assert "phone" not in public
        assert "telegram_username" not in public
        assert "whatsapp" not in public
        assert "contact" not in public


def test_public_profile_dict_contains_only_public_fields():
    with make_session() as session:
        repo = ProfileRepository(session)
        profile = repo.create(
            ProfileDraft(
                public_data={"gender": "female", "name": "سارة", "age": 25, "province": "دمشق"},
                private_contact_data={
                    "phone": "0911223344", "telegram_username": "sara25", "whatsapp": "0911223344",
                },
            )
        )
        session.commit()
        public = repo.get_public(profile.request_number)
        assert public["name"] == "سارة"
        assert "phone" not in public
        assert "telegram_username" not in public
        assert "whatsapp" not in public
