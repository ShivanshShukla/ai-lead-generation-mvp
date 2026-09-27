from pydantic import BaseModel, ConfigDict, Field


class CampaignCreate(BaseModel):
    # Trim surrounding spaces and reject values that are empty after trimming,
    # so a campaign can never be saved with a blank name, audience or offer.
    model_config = ConfigDict(str_strip_whitespace=True, str_min_length=1)

    # 255 matches the String(255) columns on the Campaign model.
    campaign_name: str = Field(max_length=255)
    industry: str = Field(max_length=255)
    location: str = Field(max_length=255)
    target_role: str = Field(max_length=255)
    offer: str


class CampaignResponse(BaseModel):
    id: int
    campaign_name: str
    industry: str
    location: str
    target_role: str
    offer: str

    class Config:
        from_attributes = True
