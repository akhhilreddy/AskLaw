import api, {
  API_BASE_URL,
  clearSessionAndRedirect,
  isTerminalRefreshFailure,
  refreshAccessToken,
} from "./api";


let controller = null;


// =========================================================
// NORMAL MESSAGE
// =========================================================

export const sendMessage = async (message) => {
  const response = await api.post(
    "/chat",
    {
      message,
    }
  );

  return response.data;
};


// =========================================================
// STREAM MESSAGE
// =========================================================

export const streamMessage = async (
  messages,
  onChunk,
  documentId = null,
) => {

  // -------------------------------------------------------
  // GET AUTH TOKEN
  // -------------------------------------------------------

  let token = localStorage.getItem(
    "token"
  );


  // -------------------------------------------------------
  // CREATE ABORT CONTROLLER
  // -------------------------------------------------------

  controller = new AbortController();


  // -------------------------------------------------------
  // SEND REQUEST
  // -------------------------------------------------------

  let timedOut = false;
  let timeoutId;

  const armTimeout = () => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller?.abort();
    }, 120000);
  };

  const request = () =>
    fetch(`${API_BASE_URL}/chat/stream`, {
      method: "POST",

      credentials: "include",

      headers: {
        "Content-Type":
          "application/json",

        Authorization:
          `Bearer ${token}`,
      },

      signal: controller.signal,

      body: JSON.stringify({
        messages,
        ...(documentId
          ? {
              document_id: documentId,
            }
          : {}),
      }),
    });

  armTimeout();

  let response;

  try {
    response = await request();

    if (response.status === 401) {
      await response.body?.cancel();

      try {
        token = await refreshAccessToken();
        response = await request();
      } catch (refreshError) {
        if (isTerminalRefreshFailure(refreshError)) {
          clearSessionAndRedirect();
          throw new Error("Your session expired. Please sign in again.", {
            cause: refreshError,
          });
        }

        throw new Error(
          "AskLAW could not refresh your session. Check your connection and try again.",
          { cause: refreshError }
        );
      }
    }
  } catch (error) {
    window.clearTimeout(timeoutId);

    if (timedOut) {
      throw new Error("The research request timed out. Please try again.", {
        cause: error,
      });
    }

    throw error;
  }


  // -------------------------------------------------------
  // CHECK RESPONSE
  // -------------------------------------------------------

  if (!response.ok) {
    window.clearTimeout(timeoutId);
    const body = await response.json().catch(() => null);

    if (response.status === 401) {
      clearSessionAndRedirect();
    }

    throw new Error(body?.detail || "The research request could not be completed.");

  }


  // -------------------------------------------------------
  // GET STREAM READER
  // -------------------------------------------------------

  const reader =
    response.body.getReader();

  const decoder =
    new TextDecoder();


  // -------------------------------------------------------
  // STORE INCOMPLETE DATA
  // -------------------------------------------------------

  let buffer = "";


  // -------------------------------------------------------
  // READ STREAM
  // -------------------------------------------------------

  while (true) {

    let readResult;

    try {
      readResult = await reader.read();
    } catch (error) {
      window.clearTimeout(timeoutId);
      controller = null;

      if (timedOut) {
        throw new Error("The research request timed out. Please try again.", {
          cause: error,
        });
      }

      throw error;
    }

    const { done, value } = readResult;


    // -----------------------------------------------------
    // STOP WHEN STREAM ENDS
    // -----------------------------------------------------

    if (done) {

      break;

    }

    armTimeout();


    // -----------------------------------------------------
    // DECODE CURRENT CHUNK
    // -----------------------------------------------------

    buffer += decoder.decode(
      value,
      {
        stream: true,
      }
    );


    // -----------------------------------------------------
    // SPLIT NDJSON EVENTS
    // -----------------------------------------------------

    const lines =
      buffer.split("\n");


    // -----------------------------------------------------
    // KEEP LAST INCOMPLETE LINE
    // -----------------------------------------------------

    buffer =
      lines.pop();


    // -----------------------------------------------------
    // PARSE EACH COMPLETE EVENT
    // -----------------------------------------------------

    for (
      const line of lines
    ) {

      if (!line.trim()) {

        continue;

      }


      try {

        const event =
          JSON.parse(line);


        // -------------------------------------------------
        // SEND PARSED EVENT TO CHAT UI
        // -------------------------------------------------

        onChunk(event);

      }

      catch (error) {

        console.error(
          "Failed to parse stream event:",
          error
        );

      }

    }

  }


  // -------------------------------------------------------
  // HANDLE FINAL BUFFER
  // -------------------------------------------------------

  if (buffer.trim()) {

    try {

      const event =
        JSON.parse(buffer);

      onChunk(event);

    }

    catch (error) {

      console.error(
        "Failed to parse final stream event:",
        error
      );

    }

  }


  // -------------------------------------------------------
  // CLEAR CONTROLLER
  // -------------------------------------------------------

  window.clearTimeout(timeoutId);
  controller = null;

};


// =========================================================
// STOP STREAMING
// =========================================================

export const stopStreaming = () => {

  if (controller) {

    controller.abort();

    controller = null;

  }

};
