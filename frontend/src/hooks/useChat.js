import { useState } from "react";
import {
  streamMessage,
  stopStreaming,
} from "../services/chatService";

export default function useChat() {
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = async (message) => {
    // Add only the user message
    const userMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
    };

    setMessages((prev) => [...prev, userMessage]);

    setIsTyping(true);
    setIsStreaming(true);

    let assistantCreated = false;
    let assistantId = crypto.randomUUID();
    let assistantResponse = "";

    try {
      await streamMessage(message, (chunk) => {
        assistantResponse += chunk;

        // First chunk
        if (!assistantCreated) {
          assistantCreated = true;

          setIsTyping(false);

          setMessages((prev) => [
            ...prev,
            {
              id: assistantId,
              role: "assistant",
              content: assistantResponse,
              isComplete: false,
            },
          ]);

          return;
        }

        // Remaining chunks
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? {
                  ...msg,
                  content: assistantResponse,
                }
              : msg
          )
        );
      });

      // Stream completed
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                isComplete: true,
              }
            : msg
        )
      );
    } catch (error) {
      if (error.name !== "AbortError") {
        console.error(error);

        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: "Sorry, something went wrong.",
            isComplete: true,
          },
        ]);
      }
    } finally {
      setIsTyping(false);
      setIsStreaming(false);
    }
  };

  const stop = () => {
    stopStreaming();

    setIsTyping(false);
    setIsStreaming(false);
  };

  return {
    messages,
    isTyping,
    isStreaming,
    sendMessage,
    stop,
  };
}