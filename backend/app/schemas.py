from typing import Annotated

from pydantic import BaseModel, Field, field_validator


PositiveId = Annotated[int, Field(gt=0)]


class CreateCampaign(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    geo: str = Field(pattern=r"^[A-Za-z]{2}$")
    offer_id: PositiveId
    domain_id: PositiveId
    group_id: PositiveId
    traffic_source_id: PositiveId

    @field_validator("geo")
    @classmethod
    def uppercase_geo(cls, value: str) -> str:
        return value.upper()


class AddOffer(BaseModel):
    offer_id: PositiveId
    expected_revision: str | None = None
