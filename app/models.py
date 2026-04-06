from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class Court(Base):
    __tablename__ = "courts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    address = Column(String, nullable=False)
    city = Column(String, nullable=False, index=True)
    zip_code = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    phone = Column(String)
    num_courts = Column(Integer)
    indoor_outdoor = Column(String)
    access_type = Column(String, index=True)
    surface_type = Column(String)
    net_type = Column(String)
    has_lights = Column(Boolean)
    hours = Column(Text)
    price_info = Column(Text)
    description = Column(Text)
    website_url = Column(String)
    source = Column(String, nullable=False, index=True)
    source_id = Column(String)
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    rating = Column(Float)
    review_count = Column(Integer)
    booking_url = Column(String)
    booking_platform = Column(String)
    photo_url = Column(String)
    is_temporary = Column(Boolean, default=False)
    schedule_notes = Column(Text)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "zip_code": self.zip_code,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "phone": self.phone,
            "num_courts": self.num_courts,
            "indoor_outdoor": self.indoor_outdoor,
            "access_type": self.access_type,
            "surface_type": self.surface_type,
            "net_type": self.net_type,
            "has_lights": self.has_lights,
            "hours": self.hours,
            "price_info": self.price_info,
            "description": self.description,
            "website_url": self.website_url,
            "source": self.source,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "rating": self.rating,
            "review_count": self.review_count,
            "booking_url": self.booking_url,
            "booking_platform": self.booking_platform,
            "photo_url": self.photo_url,
            "is_temporary": self.is_temporary,
            "schedule_notes": self.schedule_notes,
        }
