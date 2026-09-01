from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.database.repositories import ProfileFilters, ProfileRepository
from app.services.profiles import ProfileDraft


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def public_profile(name, age, residence):
    return {
        "gender": "female",
        "name": name,
        "age": age,
        "residence": residence,
        "marital_status": "عزباء",
        "occupation": "مدرسة",
        "education": "بكالوريا",
    }


def test_create_profile_assigns_unique_request_number_and_separates_contact():
    with make_session() as session:
        repo = ProfileRepository(session)
        profile = repo.create(ProfileDraft(
            public_data={**public_profile("آية", 24, "ريف دمشق - جرمانا"), "height": 165, "appearance": "محجبة", "partner_requirements": "شاب محترم"},
            private_contact_data={"phone": "0900000000", "telegram_username": "aya24", "whatsapp": "0900000000"},
        ))
        assert profile.request_number is not None
        assert repo.get_contact(profile.request_number).phone == "0900000000"
        public = repo.get_public(profile.request_number)
        assert public["name"] == "آية"
        assert public["residence"] == "ريف دمشق - جرمانا"
        assert "phone" not in public


def test_search_applies_multiple_database_filters():
    with make_session() as session:
        repo = ProfileRepository(session)
        for age, residence in [(24, "ريف دمشق - جرمانا"), (29, "دمشق"), (25, "ريف دمشق - جرمانا")]:
            repo.create(ProfileDraft(
                public_data=public_profile(f"بنت {age}", age, residence),
                private_contact_data={"phone": f"09{age}000000"},
            ))
        session.commit()
        rows = repo.search(ProfileFilters(residence="ريف دمشق", age_min=24, age_max=25))
        assert [row.age for row in rows] == [24, 25]


def test_public_repository_view_never_exposes_contact_record():
    with make_session() as session:
        repo = ProfileRepository(session)
        profile = repo.create(ProfileDraft(
            public_data=public_profile("سارة", 25, "دمشق"),
            private_contact_data={"phone": "0911223344", "telegram_username": "sara25"},
        ))
        session.commit()
        public = repo.get_public(profile.request_number)
        assert public["name"] == "سارة"
        assert public["residence"] == "دمشق"
        assert "phone" not in public
        assert "telegram_username" not in public
        assert "whatsapp" not in public
        assert "contact" not in public


def test_public_profile_dict_contains_only_public_fields():
    with make_session() as session:
        repo = ProfileRepository(session)
        profile = repo.create(ProfileDraft(
            public_data=public_profile("سارة", 25, "دمشق"),
            private_contact_data={"phone": "0911223344", "telegram_username": "sara25", "whatsapp": "0911223344"},
        ))
        session.commit()
        public = repo.get_public(profile.request_number)
        assert public["name"] == "سارة"
        assert public["residence"] == "دمشق"
        assert "phone" not in public
        assert "telegram_username" not in public
        assert "whatsapp" not in public
