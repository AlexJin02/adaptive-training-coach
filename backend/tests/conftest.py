from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, build_engine, get_db
from app.main import app
from app.services.core import initialize_defaults


@pytest.fixture
def db(tmp_path) -> Generator[Session, None, None]:  # noqa: ANN001
    test_engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(test_engine)
    local = sessionmaker(bind=test_engine, expire_on_commit=False, class_=Session)
    with local() as session:
        initialize_defaults(session)
        yield session


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:  # noqa: ANN001
    test_engine = build_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(test_engine)
    local = sessionmaker(bind=test_engine, expire_on_commit=False, class_=Session)
    with local() as session:
        initialize_defaults(session)

    def override_db():
        with local() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
