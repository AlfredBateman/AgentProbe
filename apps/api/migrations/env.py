"""Migrations run synchronously: psycopg 3 serves both modes and DDL needs no event loop."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from agentprobe_api.db import CONNECT_ARGS, normalize_url
from agentprobe_api.models import Base
from agentprobe_api.settings import get_settings

config = context.config
if config.config_file_name and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Tests pass the URL in attributes (TEST_DATABASE_URL); `pnpm db:migrate` uses DATABASE_URL.
url = config.attributes.get("url") or get_settings().database_url
if not url:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(normalize_url(url), connect_args=CONNECT_ARGS)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
