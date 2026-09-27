from pydantic import BaseModel

class CampaignCreate(BaseModel):
    campaign_name: str
    industry: str
    location: str
    target_role: str
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