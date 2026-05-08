import enum
from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class OrbitClass(enum.Enum):
    LEO = "LEO"
    MEO = "MEO"
    GEO = "GEO"
    HEO = "HEO"


class OperatorType(enum.Enum):
    GOVERNMENT = "GOVERNMENT"
    MILITARY = "MILITARY"
    COMMERCIAL = "COMMERCIAL"
    INTERNATIONAL = "INTERNATIONAL"


class ObjectType(enum.Enum):
    PAYLOAD = "PAYLOAD"
    ROCKET_BODY = "ROCKET_BODY"
    DEBRIS = "DEBRIS"
    UNKNOWN = "UNKNOWN"


class RcsSize(enum.Enum):
    LARGE = "LARGE"
    MEDIUM = "MEDIUM"
    SMALL = "SMALL"
    UNKNOWN = "UNKNOWN"


class SatelliteCategory(enum.Enum):
    STATION = "STATION"  # ISS, Tiangong
    WEATHER = "WEATHER"  # NOAA, Meteosat, GOES
    GNSS = "GNSS"  # GPS, GLONASS, Galileo, BeiDou
    MILITARY = "MILITARY"  # Military / classified
    AMATEUR = "AMATEUR"  # Amateur radio
    COMMERCIAL = "COMMERCIAL"  # Starlink, OneWeb, Iridium
    EARTH_OBS = "EARTH_OBS"  # Landsat, Sentinel, resource sats
    SCIENTIFIC = "SCIENTIFIC"  # Research / science
    OTHER = "OTHER"  # Unclassified active


_tz = DateTime(timezone=True)


class Satellite(Base):
    __tablename__ = "satellites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    norad_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    operator_country: Mapped[str | None] = mapped_column(Text)
    operator_name: Mapped[str | None] = mapped_column(Text)
    operator_type: Mapped[OperatorType | None] = mapped_column(
        Enum(OperatorType, name="operator_type")
    )
    orbit_class: Mapped[OrbitClass | None] = mapped_column(
        Enum(OrbitClass, name="orbit_class_type")
    )
    launch_date: Mapped[date | None] = mapped_column(Date)
    decay_date: Mapped[date | None] = mapped_column(Date)
    international_designator: Mapped[str | None] = mapped_column(Text)
    object_type: Mapped[ObjectType | None] = mapped_column(
        Enum(ObjectType, name="object_type")
    )
    rcs_size: Mapped[RcsSize | None] = mapped_column(Enum(RcsSize, name="rcs_size"))
    category: Mapped[SatelliteCategory | None] = mapped_column(
        Enum(SatelliteCategory, name="satellite_category"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(_tz, server_default="now()")

    tle_snapshots: Mapped[list["TleSnapshot"]] = relationship(
        back_populates="satellite"
    )
    predicted_passes: Mapped[list["PredictedPass"]] = relationship(
        back_populates="satellite"
    )
    actual_passes: Mapped[list["ActualPass"]] = relationship(back_populates="satellite")


class TleSnapshot(Base):
    __tablename__ = "tle_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    satellite_id: Mapped[int] = mapped_column(
        ForeignKey("satellites.id"), nullable=False
    )
    line1: Mapped[str] = mapped_column(CHAR(69), nullable=False)
    line2: Mapped[str] = mapped_column(CHAR(69), nullable=False)
    epoch: Mapped[datetime] = mapped_column(_tz, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(_tz, server_default="now()")

    satellite: Mapped[Satellite] = relationship(back_populates="tle_snapshots")

    __table_args__ = (
        Index("ix_tle_snapshots_satellite_ingested", "satellite_id", "ingested_at"),
    )


class PredictedPass(Base):
    __tablename__ = "predicted_passes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    satellite_id: Mapped[int] = mapped_column(
        ForeignKey("satellites.id"), nullable=False
    )
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    tle_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("tle_snapshots.id"), nullable=False
    )
    entry_time: Mapped[datetime] = mapped_column(_tz, nullable=False)
    exit_time: Mapped[datetime] = mapped_column(_tz, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_lat: Mapped[float | None]
    entry_lon: Mapped[float | None]
    exit_lat: Mapped[float | None]
    exit_lon: Mapped[float | None]
    predicted_at: Mapped[datetime] = mapped_column(_tz, nullable=False)

    satellite: Mapped[Satellite] = relationship(back_populates="predicted_passes")

    __table_args__ = (
        Index("ix_predicted_passes_country_entry", "country_code", "entry_time"),
        Index("ix_predicted_passes_satellite_entry", "satellite_id", "entry_time"),
    )


class ActualPass(Base):
    __tablename__ = "actual_passes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    satellite_id: Mapped[int] = mapped_column(
        ForeignKey("satellites.id"), nullable=False
    )
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    tle_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("tle_snapshots.id"), nullable=False
    )
    entry_time: Mapped[datetime] = mapped_column(_tz, nullable=False)
    exit_time: Mapped[datetime] = mapped_column(_tz, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_lat: Mapped[float | None]
    entry_lon: Mapped[float | None]
    exit_lat: Mapped[float | None]
    exit_lon: Mapped[float | None]
    predicted_pass_id: Mapped[int | None] = mapped_column(
        ForeignKey("predicted_passes.id"), nullable=True
    )
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    satellite: Mapped[Satellite] = relationship(back_populates="actual_passes")

    __table_args__ = (
        Index("ix_actual_passes_country_entry", "country_code", "entry_time"),
        Index("ix_actual_passes_satellite_entry", "satellite_id", "entry_time"),
    )
