const DEFAULT_SIGNUP_ERROR = "Signup failed. Please try again.";
const NETWORK_SIGNUP_ERROR =
  "Unable to reach the server. Please check your connection and try again.";

const LOCATION_PREFIXES = new Set([
  "body",
  "cookie",
  "header",
  "path",
  "query",
]);

const ensureSentence = (message) => {
  const trimmed = message.trim();

  if (!trimmed || /[.!?]$/.test(trimmed)) {
    return trimmed;
  }

  return `${trimmed}.`;
};

const getFieldLabel = (location) => {
  if (!Array.isArray(location)) {
    return "";
  }

  const field = [...location]
    .reverse()
    .find(
      (part) =>
        typeof part === "string" &&
        part.trim() &&
        !LOCATION_PREFIXES.has(part.toLowerCase()),
    );

  if (!field) {
    return "";
  }

  const label = field.replace(/[_-]+/g, " ").trim();
  return label.charAt(0).toUpperCase() + label.slice(1);
};

const normalizeValidationItem = (item) => {
  if (typeof item === "string") {
    return ensureSentence(item);
  }

  if (!item || typeof item !== "object") {
    return "";
  }

  const message =
    typeof item.msg === "string"
      ? item.msg.trim()
      : typeof item.message === "string"
        ? item.message.trim()
        : "";
  const field = getFieldLabel(item.loc);

  if (!message) {
    return "";
  }

  if (item.type === "missing" || message.toLowerCase() === "field required") {
    return field ? `${field} is required.` : "A required field is missing.";
  }

  if (/valid email address/i.test(message)) {
    return field
      ? `${field} must be a valid email address.`
      : "Enter a valid email address.";
  }

  return field
    ? `${field}: ${ensureSentence(message)}`
    : ensureSentence(message);
};

const normalizeDetail = (detail) => {
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  if (Array.isArray(detail)) {
    const messages = detail.map(normalizeValidationItem).filter(Boolean);
    return messages.join("\n");
  }

  if (detail && typeof detail === "object") {
    return normalizeValidationItem(detail);
  }

  return "";
};

export const normalizeSignupError = (error) => {
  const responseData = error?.response?.data;

  if (error?.response) {
    const detailMessage = normalizeDetail(responseData?.detail);

    if (detailMessage) {
      return detailMessage;
    }

    if (typeof responseData?.message === "string" && responseData.message.trim()) {
      return responseData.message.trim();
    }

    return DEFAULT_SIGNUP_ERROR;
  }

  if (
    error?.request ||
    error?.code === "ERR_NETWORK" ||
    error?.message === "Network Error"
  ) {
    return NETWORK_SIGNUP_ERROR;
  }

  if (typeof error === "string" && error.trim()) {
    return error.trim();
  }

  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message.trim();
  }

  return DEFAULT_SIGNUP_ERROR;
};

