import api from "./api";

let controller = null;

export const sendMessage = async (message) => {
  const response = await api.post("/chat", {
    message,
  });

  return response.data;
};

export const streamMessage = async (
  message,
  onChunk
) => {
  const token = localStorage.getItem("token");

  controller = new AbortController();

  const response = await fetch(
    "http://localhost:8000/chat/stream",
    {
      method: "POST",
      credentials: "include",

      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },

      signal: controller.signal,

      body: JSON.stringify({
        message,
      }),
    }
  );

  if (!response.ok) {
    throw new Error("Failed to stream response");
  }

  const reader = response.body.getReader();

  const decoder = new TextDecoder();

  while (true) {
    const { done, value } =
      await reader.read();

    if (done) break;

    onChunk(
      decoder.decode(value)
    );
  }
};

export const stopStreaming = () => {
  if (controller) {
    controller.abort();
    controller = null;
  }
};