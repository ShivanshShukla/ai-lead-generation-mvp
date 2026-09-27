import { useState } from "react";
import CampaignForm from "../components/CampaignForm";
import CampaignList from "../components/CampaignList";
import PageHeader from "../components/ui/PageHeader";

function Campaigns() {
  const [refreshKey, setRefreshKey] = useState(0);

  const refreshCampaigns = () => {
    setRefreshKey((currentKey) => currentKey + 1);
  };

  return (
    <div>
      <PageHeader
        title="Campaigns"
        description="Create focused outreach campaigns and keep offer, industry, role, and location context together."
      />
      <div className="space-y-6">
        <CampaignForm onCampaignCreated={refreshCampaigns} />
        <CampaignList refreshKey={refreshKey} />
      </div>
    </div>
  );
}

export default Campaigns;
