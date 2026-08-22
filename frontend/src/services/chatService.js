import api from "./api";


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
  onChunk
) => {

  // -------------------------------------------------------
  // GET AUTH TOKEN
  // -------------------------------------------------------

  const token = localStorage.getItem(
    "token"
  );


  // -------------------------------------------------------
  // CREATE ABORT CONTROLLER
  // -------------------------------------------------------

  controller = new AbortController();


  // -------------------------------------------------------
  // SEND REQUEST
  // -------------------------------------------------------

  const response = await fetch(
    "http://localhost:8000/chat/stream",
    {
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
      }),
    }
  );


  // -------------------------------------------------------
  // CHECK RESPONSE
  // -------------------------------------------------------

  if (!response.ok) {

    throw new Error(
      "Failed to stream response"
    );

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

    const { done, value } =
      await reader.read();


    // -----------------------------------------------------
    // STOP WHEN STREAM ENDS
    // -----------------------------------------------------

    if (done) {

      break;

    }


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