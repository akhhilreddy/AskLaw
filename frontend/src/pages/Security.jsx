import { useCallback, useEffect, useState } from "react";
import { Fingerprint, KeyRound, ShieldCheck } from "lucide-react";

import AppLayout from "../layout/AppLayout";
import { getMe } from "../services/authService";
import {
  getPasskeys,
  isPasskeySupported,
  passkeyErrorMessage,
  registerPasskey,
  removePasskey,
} from "../services/passkeyService";


const formatDate = (value) => {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};


export default function Security() {
  const [userName, setUserName] = useState("Account");
  const [passkeys, setPasskeys] = useState([]);
  const [name, setName] = useState("My passkey");
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [confirmingId, setConfirmingId] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const supported = isPasskeySupported();

  const loadPasskeys = useCallback(async () => {
    const records = await getPasskeys();
    setPasskeys(Array.isArray(records) ? records : []);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([getMe(), getPasskeys()])
      .then(([user, records]) => {
        if (!active) return;
        if (user?.name) setUserName(user.name);
        setPasskeys(Array.isArray(records) ? records : []);
      })
      .catch((requestError) => {
        if (active) {
          setError(
            requestError.response?.data?.detail ||
              "Could not load your security settings."
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleRegister = async (event) => {
    event.preventDefault();
    if (!name.trim() || registering) return;
    setRegistering(true);
    setError("");
    setMessage("");
    try {
      await registerPasskey(name.trim());
      await loadPasskeys();
      setMessage("Passkey added. You can now use it to sign in.");
      setName("My passkey");
    } catch (requestError) {
      setError(
        passkeyErrorMessage(requestError, "Could not add the passkey.")
      );
    } finally {
      setRegistering(false);
    }
  };

  const handleDelete = async (credentialId) => {
    setDeletingId(credentialId);
    setError("");
    setMessage("");
    try {
      await removePasskey(credentialId);
      setPasskeys((current) =>
        current.filter((passkey) => passkey.id !== credentialId)
      );
      setConfirmingId(null);
      setMessage("Passkey removed.");
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "Could not remove the passkey."
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <AppLayout userName={userName}>
      <div className="security-page">
        <span className="eyebrow">Account security</span>
        <h1>Passkeys</h1>
        <p>
          Add a passkey using Touch ID on Mac or Face ID on iPhone, then sign
          in without entering a password.
        </p>

        <div className="security-summary" aria-label="Passkey security details">
          <span><ShieldCheck size={17} aria-hidden="true" /> Phishing resistant</span>
          <span><KeyRound size={17} aria-hidden="true" /> Bound to AskLAW</span>
          <span><Fingerprint size={17} aria-hidden="true" /> Biometric data stays on your device</span>
        </div>

        {!supported && (
          <div className="security-notice" role="status">
            This browser does not support passkeys. Use a current version of
            Safari, Chrome, Edge, or Firefox.
          </div>
        )}

        <section className="security-panel" aria-labelledby="add-passkey-title">
          <div>
            <h2 id="add-passkey-title">Add a passkey</h2>
            <p>Name this passkey so you can recognize it later.</p>
          </div>
          <form className="passkey-register-form" onSubmit={handleRegister}>
            <label htmlFor="passkey-name">Passkey name</label>
            <div>
              <input
                id="passkey-name"
                value={name}
                maxLength={80}
                onChange={(event) => setName(event.target.value)}
                disabled={!supported || registering}
              />
              <button
                className="primary-button"
                type="submit"
                disabled={!supported || registering || !name.trim()}
              >
                {registering ? "Waiting for device…" : "Add passkey"}
              </button>
            </div>
          </form>
        </section>

        <section className="security-panel" aria-labelledby="your-passkeys-title">
          <div>
            <h2 id="your-passkeys-title">Your passkeys</h2>
            <p>Remove a passkey if a device or password manager is no longer trusted.</p>
          </div>
          {loading ? (
            <p className="passkey-empty" role="status">Loading passkeys…</p>
          ) : passkeys.length === 0 ? (
            <p className="passkey-empty">No passkeys registered yet.</p>
          ) : (
            <div className="passkey-list">
              {passkeys.map((passkey) => (
                <div className="passkey-row" key={passkey.id}>
                  <div className="passkey-icon"><Fingerprint size={20} /></div>
                  <div className="passkey-details">
                    <strong>{passkey.name}</strong>
                    <span>
                      Added {formatDate(passkey.created_at)} · Last used {formatDate(passkey.last_used_at)}
                    </span>
                    {passkey.backed_up && <small>Synced passkey</small>}
                  </div>
                  {confirmingId === passkey.id ? (
                    <div className="passkey-confirm-actions">
                      <button type="button" onClick={() => setConfirmingId(null)} disabled={deletingId === passkey.id}>Cancel</button>
                      <button type="button" className="danger-action" onClick={() => handleDelete(passkey.id)} disabled={deletingId === passkey.id}>
                        {deletingId === passkey.id ? "Removing…" : "Confirm remove"}
                      </button>
                    </div>
                  ) : (
                    <button type="button" className="passkey-remove" onClick={() => setConfirmingId(passkey.id)}>Remove</button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="security-feedback" aria-live="polite">
          {message && <p className="auth-status">{message}</p>}
          {error && <p className="field-error auth-server-error" role="alert">{error}</p>}
        </div>
      </div>
    </AppLayout>
  );
}
