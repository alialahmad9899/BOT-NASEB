from app.database.models import Base, Profile
from app.database.repositories import ProfileRepository
from app.services.profiles import ProfileDraft
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _draft(name: str = "آية") -> ProfileDraft:
    return ProfileDraft(
        public_data={
            "gender": "female",
            "name": name,
            "age": 25,
            "residence": "دمشق",
            "marital_status": "عزباء",
            "children_count": 0,
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


def test_next_request_number_starts_at_200_on_empty_database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ProfileRepository(session)

        assert repository.peek_next_request_number() == 200

        first = repository.create(_draft("آية"))
        first_number = first.request_number
        session.commit()

        assert first_number == 200
        assert repository.peek_next_request_number() == 201

        second = repository.create(_draft("سارة"))
        second_number = second.request_number
        session.commit()

    assert second_number == 201


def test_existing_request_numbers_are_preserved_and_next_number_continues_from_200():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Profile(
                request_number=150,
                gender="female",
                name="إعلان قديم",
                age=30,
                residence="حمص",
                status="active",
            )
        )
        session.commit()

        repository = ProfileRepository(session)
        assert repository.peek_next_request_number() == 200

        created = repository.create(_draft("إعلان جديد"))
        created_number = created.request_number
        session.commit()

    assert created_number == 200
