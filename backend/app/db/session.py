from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # pool_recycle: Supabase's pooler/network can silently drop an idle
    # connection well before pool_pre_ping's cheap check would catch a truly
    # dead socket in every case; recycling proactively avoids relying on that
    # alone. connect_timeout: bounds the TCP-connect-plus-auth phase, which
    # previously had no explicit bound at all (a network partition to the DB
    # host could hang a request far past every other timeout budget in this
    # codebase). Both are libpq keywords, valid for the psycopg v3 driver.
    pool_recycle=1800,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
