"""Shared test setup.

The environment is set before any application module is imported, because
app.core.config builds Settings at import time. Every external credential is
forced to a fake or empty value: environment variables take precedence over the
developer's .env, so no test can reach the real OpenAI or Telegram, even by
accident. The database is a dedicated one, and its name must end in "_test".
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://amazonbot:amazonbot@localhost:5432/amazonbot_test",
)

if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError(
        "Refusing to run: the test database name must end in '_test', so the "
        "tests can never touch a development or production database."
    )

os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL,
        "APP_API_KEY": "test-api-key",
        "AMAZON_PARTNER_TAG": "test-20",
        "OPENAI_API_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "SCHEDULER_ENABLED": "false",
        "DELIVERY_MAX_ATTEMPTS": "3",
    }
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def make_promotion():
    """Build an unsaved Promotion; any field can be overridden."""
    from app.models.promotions import Promotion, PromotionStatus

    def _make(**overrides) -> Promotion:
        values = {
            "asin": "B0CNOTE001",
            "title": "Notebook Acer Aspire 5",
            "original_price": Decimal("4299.90"),
            "discounted_price": Decimal("3299.90"),
            "discount_percentage": Decimal("23.26"),
            "product_url": "https://www.amazon.com.br/dp/B0CNOTE001",
            "image_url": None,
            "category": "Computers",
            "status": PromotionStatus.PENDING,
            "attempts": 0,
            "generated_message": None,
        }
        values.update(overrides)
        return Promotion(**values)

    return _make


@pytest.fixture(scope="session")
def test_engine():
    """Recreate the test database and migrate it from scratch.

    Starting from an empty database every run also proves that the whole
    migration chain applies cleanly, not only the latest migration.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    from app.db.database import engine

    url = make_url(TEST_DATABASE_URL)

    # If anything imported the application before this module set DATABASE_URL,
    # the engine would be bound to the developer's database, and the migrations
    # below would run there. Refuse instead.
    if engine.url.database != url.database:
        raise RuntimeError(
            f"Application engine is bound to {engine.url.database!r}, "
            f"not the test database {url.database!r}"
        )

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            # The name was checked to end in "_test" when this module loaded.
            connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError:
        pytest.skip("test database unavailable; start it with: docker compose up -d")
    finally:
        admin.dispose()

    # Built without alembic.ini on purpose: its logging section would replace
    # the handlers pytest uses to capture logs.
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(config, "head")

    return engine


@pytest.fixture
def db_session(test_engine):
    """A session whose work is undone after each test.

    The repository commits on its own; join_transaction_mode="create_savepoint"
    turns those commits into savepoints inside one outer transaction, which is
    rolled back at the end, so no test ever sees another test's rows.
    """
    from sqlalchemy.orm import Session

    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()
