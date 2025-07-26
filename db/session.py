import os

from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool.impl import NullPool

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "The DATABASE_URL environment variable is not set. "
        "Please ensure it is defined in a .env file in the project root."
    )

connection_arguments = {
    "prepare_threshold": None
}

engine = create_engine(
    DATABASE_URL,
    connect_args=connection_arguments,
    poolclass=NullPool
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    register_vector(dbapi_connection)

def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
