import api from "./api";

const base64urlToBuffer = (value) => {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  const binary = window.atob(padded);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes.buffer;
};

const bufferToBase64url = (value) => {
  const bytes = new Uint8Array(value);
  let binary = "";

  for (const byte of bytes) binary += String.fromCharCode(byte);

  return window
    .btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
};

const creationOptionsFromJSON = (options) => ({
  ...options,
  challenge: base64urlToBuffer(options.challenge),
  user: {
    ...options.user,
    id: base64urlToBuffer(options.user.id),
  },
  excludeCredentials: (options.excludeCredentials || []).map((credential) => ({
    ...credential,
    id: base64urlToBuffer(credential.id),
  })),
});

const requestOptionsFromJSON = (options) => ({
  ...options,
  challenge: base64urlToBuffer(options.challenge),
  allowCredentials: (options.allowCredentials || []).map((credential) => ({
    ...credential,
    id: base64urlToBuffer(credential.id),
  })),
});

const credentialToJSON = (credential) => {
  const response = credential.response;
  const serialized = {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
    },
  };

  if ("attestationObject" in response) {
    serialized.response.attestationObject = bufferToBase64url(
      response.attestationObject
    );
    serialized.response.transports = response.getTransports?.() || [];
  } else {
    serialized.response.authenticatorData = bufferToBase64url(
      response.authenticatorData
    );
    serialized.response.signature = bufferToBase64url(response.signature);
    serialized.response.userHandle = response.userHandle
      ? bufferToBase64url(response.userHandle)
      : null;
  }

  return serialized;
};

export const isPasskeySupported = () =>
  typeof window !== "undefined" &&
  Boolean(window.PublicKeyCredential && navigator.credentials);

export const authenticateWithPasskey = async () => {
  if (!isPasskeySupported()) {
    throw new Error("Passkeys are not supported in this browser.");
  }

  const optionsResponse = await api.post(
    "/auth/passkeys/authenticate/options",
    {}
  );
  const { flow_id: flowId, options } = optionsResponse.data;
  const credential = await navigator.credentials.get({
    publicKey: requestOptionsFromJSON(options),
  });

  if (!credential) throw new Error("No passkey was selected.");

  const verificationResponse = await api.post(
    "/auth/passkeys/authenticate/verify",
    {
      flow_id: flowId,
      credential: credentialToJSON(credential),
    }
  );
  return verificationResponse.data;
};

export const registerPasskey = async (name) => {
  if (!isPasskeySupported()) {
    throw new Error("Passkeys are not supported in this browser.");
  }

  const optionsResponse = await api.post(
    "/auth/passkeys/register/options",
    {}
  );
  const { flow_id: flowId, options } = optionsResponse.data;
  const credential = await navigator.credentials.create({
    publicKey: creationOptionsFromJSON(options),
  });

  if (!credential) throw new Error("Passkey creation was cancelled.");

  const verificationResponse = await api.post(
    "/auth/passkeys/register/verify",
    {
      flow_id: flowId,
      credential: credentialToJSON(credential),
      name,
    }
  );
  return verificationResponse.data;
};

export const getPasskeys = async () => {
  const response = await api.get("/auth/passkeys");
  return response.data;
};

export const removePasskey = async (credentialId) => {
  await api.delete(`/auth/passkeys/${encodeURIComponent(credentialId)}`);
};

export const passkeyErrorMessage = (error, fallback) => {
  if (error?.name === "NotAllowedError") {
    return "The passkey request was cancelled or timed out.";
  }
  if (error?.name === "InvalidStateError") {
    return "This passkey is already registered for your account.";
  }
  return error?.response?.data?.detail || error?.message || fallback;
};
