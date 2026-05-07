from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

_tz = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_tz, server_default="now()")

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(back_populates="user")
    passkey_credentials: Mapped[list["PasskeyCredential"]] = relationship(
        back_populates="user"
    )
    country_bookmarks: Mapped[list["CountryBookmark"]] = relationship(
        back_populates="user"
    )
    satellite_bookmarks: Mapped[list["SatelliteBookmark"]] = relationship(
        back_populates="user"
    )


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(_tz, server_default="now()")

    user: Mapped[User] = relationship(back_populates="oauth_accounts")

    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    credential_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(_tz, server_default="now()")

    user: Mapped[User] = relationship(back_populates="passkey_credentials")


class CountryBookmark(Base):
    __tablename__ = "country_bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(_tz, server_default="now()")

    user: Mapped[User] = relationship(back_populates="country_bookmarks")

    __table_args__ = (UniqueConstraint("user_id", "country_code"),)


class SatelliteBookmark(Base):
    __tablename__ = "satellite_bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    satellite_id: Mapped[int] = mapped_column(
        ForeignKey("satellites.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(_tz, server_default="now()")

    user: Mapped[User] = relationship(back_populates="satellite_bookmarks")

    __table_args__ = (UniqueConstraint("user_id", "satellite_id"),)
