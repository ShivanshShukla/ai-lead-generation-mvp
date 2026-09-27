import { useEffect, useState } from "react";
import { getHunterStatus } from "../api/hunter";
import api from "../services/api";
import { getFriendlyErrorMessage } from "../utils/errorMessages";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import PageHeader from "../components/ui/PageHeader";

function Settings() {
  const [gmailStatus, setGmailStatus] = useState({
    connected: false,
    email: "",
    replyTrackingAvailable: false,
  });
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isConnecting, setIsConnecting] = useState(false);
  const [showAuthorizationHint, setShowAuthorizationHint] = useState(false);
  const [statusError, setStatusError] = useState("");
  const [hunterStatus, setHunterStatus] = useState(null);
  const [isLoadingHunterStatus, setIsLoadingHunterStatus] = useState(true);
  const [hunterStatusError, setHunterStatusError] = useState("");

  const fetchGmailStatus = async () => {
    setIsLoadingStatus(true);
    setStatusError("");

    try {
      const res = await api.get("/gmail/status");
      setGmailStatus({
        connected: Boolean(res.data.connected),
        email: res.data.email || "",
        replyTrackingAvailable: Boolean(res.data.reply_tracking_available),
      });

      if (res.data.connected) {
        setShowAuthorizationHint(false);
      }
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Could not load Gmail connection status."));
      console.error(err);
    } finally {
      setIsLoadingStatus(false);
    }
  };

  const fetchHunterConnectionStatus = async () => {
    setIsLoadingHunterStatus(true);
    setHunterStatusError("");

    try {
      const status = await getHunterStatus();
      setHunterStatus(status);
    } catch (err) {
      setHunterStatusError(getFriendlyErrorMessage(err, "Could not load Hunter.io status."));
      console.error(err);
    } finally {
      setIsLoadingHunterStatus(false);
    }
  };

  useEffect(() => {
    let isMounted = true;

    const loadGmailStatus = async () => {
      try {
        const res = await api.get("/gmail/status");

        if (!isMounted) {
          return;
        }

        setGmailStatus({
          connected: Boolean(res.data.connected),
          email: res.data.email || "",
          replyTrackingAvailable: Boolean(res.data.reply_tracking_available),
        });

        if (res.data.connected) {
          setShowAuthorizationHint(false);
        }
      } catch (err) {
        if (isMounted) {
          setStatusError(getFriendlyErrorMessage(err, "Could not load Gmail connection status."));
        }
        console.error(err);
      } finally {
        if (isMounted) {
          setIsLoadingStatus(false);
        }
      }
    };

    const loadHunterStatus = async () => {
      try {
        const status = await getHunterStatus();

        if (!isMounted) {
          return;
        }

        setHunterStatus(status);
      } catch (err) {
        if (isMounted) {
          setHunterStatusError(getFriendlyErrorMessage(err, "Could not load Hunter.io status."));
        }
        console.error(err);
      } finally {
        if (isMounted) {
          setIsLoadingHunterStatus(false);
        }
      }
    };

    loadGmailStatus();
    loadHunterStatus();

    return () => {
      isMounted = false;
    };
  }, []);

  const handleConnectGmail = async () => {
    setIsConnecting(true);
    setShowAuthorizationHint(false);
    setStatusError("");

    try {
      const res = await api.get("/gmail/oauth/start");
      const authUrl = res.data.auth_url;

      if (!authUrl) {
        throw new Error("Missing Gmail authorization URL.");
      }

      window.open(authUrl, "_blank", "noopener,noreferrer");
      setShowAuthorizationHint(true);
    } catch (err) {
      setStatusError(getFriendlyErrorMessage(err, "Could not start Gmail connection."));
      console.error(err);
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Manage Gmail connection and safety controls for sending and reply tracking."
      />

      <div className="space-y-6">
        <Card>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xl font-semibold tracking-tight text-ink">Gmail Connection</h3>
                {!isLoadingStatus && (
                  <Badge variant={gmailStatus.connected ? "success" : "neutral"}>
                    {gmailStatus.connected ? "Connected" : "Not connected"}
                  </Badge>
                )}
              </div>
              <p className="mt-2 text-sm text-muted">
                Gmail sending is restricted to approved drafts and approved follow-ups only.
              </p>
              <p className="mt-1 text-sm text-muted">
                Reply tracking requires Gmail readonly permission. If reply check fails, reconnect Gmail.
              </p>
              <p className="mt-1 text-sm text-muted">
                AI reply classification only suggests next actions. It does not send replies automatically.
              </p>
              <p className="mt-1 text-sm text-muted">
                AI response drafts require approval before sending.
              </p>
            </div>

            <Button
              type="button"
              variant="secondary"
              className="w-full sm:w-auto"
              disabled={isLoadingStatus}
              onClick={fetchGmailStatus}
            >
              Refresh Status
            </Button>
          </div>

          <div className="mt-5 rounded-3xl border line-1 surface-sunk p-4 sm:p-5">
            {isLoadingStatus ? (
              <p className="text-sm text-ink-2">Checking Gmail connection...</p>
            ) : gmailStatus.connected ? (
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="break-words text-sm font-semibold text-success">
                    {gmailStatus.email ? `Gmail connected as ${gmailStatus.email}` : "Gmail connected"}
                  </p>
                  <p className="mt-1 text-sm text-ink-2">Approved drafts and approved follow-ups can be sent from the Emails page.</p>
                  <p className="mt-1 text-sm text-ink-2">
                    Reconnect Gmail if reply tracking is not available.
                  </p>
                  {!gmailStatus.replyTrackingAvailable && (
                    <p className="mt-2 text-sm font-medium text-warn">
                      Gmail readonly permission may be missing.
                    </p>
                  )}
                </div>

                <Button
                  type="button"
                  className="w-full sm:w-auto"
                  disabled={isConnecting}
                  onClick={handleConnectGmail}
                >
                  {isConnecting ? "Opening Gmail..." : "Reconnect Gmail"}
                </Button>
              </div>
            ) : (
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-ink">Gmail not connected</p>
                  <p className="mt-1 text-sm text-muted">
                    Connect Gmail to send approved email drafts.
                  </p>
                </div>

                <Button
                  type="button"
                  className="w-full sm:w-auto"
                  disabled={isConnecting}
                  onClick={handleConnectGmail}
                >
                  {isConnecting ? "Opening Gmail..." : "Connect Gmail"}
                </Button>
              </div>
            )}
          </div>

          {showAuthorizationHint && (
            <p className="mt-4 rounded-lg border border-info-soft bg-info-soft p-3 text-sm text-info">
              Complete Gmail authorization in the new tab, then refresh the status here.
            </p>
          )}

          {statusError && (
            <p className="mt-4 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
              {statusError}
            </p>
          )}
        </Card>

        <Card>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xl font-semibold tracking-tight text-ink">Hunter.io Enrichment</h3>
                {!isLoadingHunterStatus && hunterStatus && (
                  <Badge variant={hunterStatus.configured ? "success" : "warning"}>
                    {hunterStatus.configured ? "Configured" : "Not configured"}
                  </Badge>
                )}
                {!isLoadingHunterStatus && hunterStatus?.is_test_key && (
                  <Badge variant="warning">Test key</Badge>
                )}
              </div>
              <p className="mt-2 text-sm text-muted">
                Hunter can find professional emails from a lead website when public extraction does not find one.
              </p>
              <p className="mt-1 text-sm text-muted">
                Bulk enrichment uses credits, so the Leads page caps each run.
              </p>
            </div>

            <Button
              type="button"
              variant="secondary"
              className="w-full sm:w-auto"
              disabled={isLoadingHunterStatus}
              onClick={fetchHunterConnectionStatus}
            >
              Refresh Status
            </Button>
          </div>

          <div className="mt-5 rounded-3xl border line-1 surface-sunk p-4 sm:p-5">
            {isLoadingHunterStatus ? (
              <p className="text-sm text-ink-2">Checking Hunter.io status...</p>
            ) : hunterStatus ? (
              <p className={hunterStatus.configured ? "text-sm font-semibold text-success" : "text-sm font-semibold text-warn"}>
                {hunterStatus.message}
              </p>
            ) : (
              <p className="text-sm text-ink-2">Hunter.io status unavailable.</p>
            )}
          </div>

          {hunterStatusError && (
            <p className="mt-4 rounded-lg border border-danger-soft bg-danger-soft p-3 text-sm text-danger">
              {hunterStatusError}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}

export default Settings;
