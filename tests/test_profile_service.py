import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.users import add_user
from app.db.models import ProfileVector, SeedPaper, Topic, User
from app.domain.ranking import ProfileCoefficients
from app.domain.seeds import SeedRefs
from app.embeddings.base import EmbeddingError, Embeddings
from app.profiles import service
from app.profiles.topics import ProposedTopic
from tests.fakes import FakeEmbedder, FakePubMed

pytestmark = pytest.mark.db

COEFS = ProfileCoefficients()


@pytest.fixture
def user(db_session: Session) -> User:
    return add_user(db_session, "surgeon@example.com")


class FailingEmbedder(FakeEmbedder):
    def embed(self, texts: list[str], input_type: str) -> Embeddings:
        raise EmbeddingError("rate limited")


def test_replace_topics_keeps_unchanged_embeddings(db_session: Session, user: User) -> None:
    e = FakeEmbedder()
    service.replace_topics(db_session, user.id, [ProposedTopic("A", "alpha")], "onboarding")
    assert service.embed_topics(db_session, e) == 1
    service.replace_topics(
        db_session,
        user.id,
        [ProposedTopic("A renamed", "alpha"), ProposedTopic("B", "beta")],
        "manual",
    )
    assert service.embed_topics(db_session, e) == 1  # only "beta" is new
    assert service.embed_topics(db_session, FakeEmbedder(model="voyage-5")) == 2
    assert [t.label for t in service.active_topics(db_session, user.id)] == ["A renamed", "B"]


def test_sync_embeddings_survives_provider_failure(db_session: Session, user: User) -> None:
    service.replace_topics(db_session, user.id, [ProposedTopic("A", "alpha")], "onboarding")
    assert not service.sync_embeddings(db_session, FailingEmbedder(), user.id, COEFS)
    assert db_session.scalars(select(Topic.embedding_model)).one() is None
    assert service.sync_embeddings(db_session, FakeEmbedder(), user.id, COEFS)
    assert db_session.get(ProfileVector, user.id) is not None


def test_profile_vector_uses_seeds_and_drops_when_empty(db_session: Session, user: User) -> None:
    e = FakeEmbedder()
    service.add_seeds(db_session, user.id, SeedRefs(pmids=["42958619"]), FakePubMed())  # type: ignore[arg-type]
    assert service.sync_embeddings(db_session, e, user.id, COEFS)  # seeds alone are enough
    pv = db_session.get(ProfileVector, user.id)
    assert pv is not None and pv.model == "voyage-4"
    service.remove_seed(db_session, user.id, "42958619")
    assert not service.refresh_profile_vector(db_session, user.id, "voyage-4", COEFS)
    db_session.expire_all()
    assert db_session.get(ProfileVector, user.id) is None


def test_add_seeds_is_idempotent_and_reuses_stored_papers(db_session: Session, user: User) -> None:
    pubmed = FakePubMed()
    refs = SeedRefs(pmids=["42958619"], dois=["10.1111/cid.70192"])  # same paper twice
    first = service.add_seeds(db_session, user.id, refs, pubmed)  # type: ignore[arg-type]
    second = service.add_seeds(db_session, user.id, refs, pubmed)  # type: ignore[arg-type]
    assert first.added == second.added == ["42958619"]
    assert pubmed.fetched == [["42958619"]]  # second call found it in the database
    assert db_session.scalars(select(SeedPaper.pmid)).all() == ["42958619"]


def test_refresh_all_profiles(db_session: Session, user: User) -> None:
    other = add_user(db_session, "other@example.com")
    for u in (user, other):
        service.replace_topics(db_session, u.id, [ProposedTopic("A", f"alpha {u.email}")], "manual")
    service.embed_topics(db_session, FakeEmbedder())
    assert service.refresh_all_profiles(db_session, "voyage-4", COEFS) == 2
