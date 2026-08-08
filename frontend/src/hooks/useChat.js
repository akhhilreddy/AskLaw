import { useEffect, useState } from "react";

import {
  streamMessage,
  stopStreaming,
} from "../services/chatService";

import {
  createConversation as createConversationApi,
  addMessage,
  getConversation,
  getConversations,
  updateConversationTitle,
} from "../services/conversationService";

export default function useChat() {
  const [conversation, setConversation] = useState({
    id: null,
    title: "New Chat",
    messages: [],
  });

  const [conversations, setConversations] = useState([]);

  const [isTyping, setIsTyping] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);

  // Load all conversations for the logged-in user
  const loadConversations = async () => {
    try {
      const data = await getConversations();

      setConversations(data);
    } catch (error) {
      console.error(
        "Failed to load conversations:",
        error
      );
    }
  };

  // Load conversations when AskLaw opens
  useEffect(() => {
    loadConversations();
  }, []);

  const sendMessage = async (message) => {
    let conversationId = conversation.id;

    try {
      // Create a MongoDB conversation if one doesn't exist yet
      if (!conversationId) {
        const newConversation =
          await createConversationApi();

        conversationId = newConversation.id;

        setConversation((prev) => ({
          ...prev,
          id: newConversation.id,
          title: newConversation.title,
        }));

        // Refresh the conversation list
        await loadConversations();
      }

      const userMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: message,
      };

      // Build AI context.
      // Only the latest 12 messages are sent to Ollama.
      const conversationContext = [
        ...conversation.messages
          .slice(-12)
          .map(({ role, content }) => ({
            role,
            content,
          })),
        {
          role: "user",
          content: message,
        },
      ];

      // Show user's message immediately
      setConversation((prev) => ({
        ...prev,
        messages: [
          ...prev.messages,
          userMessage,
        ],
      }));

      // Save user message to MongoDB
      await addMessage(
        conversationId,
        "user",
        message
      );

      if (conversation.messages.length === 0) {
        const titleResponse =
          await updateConversationTitle(conversationId);

        if (titleResponse?.title) {
          setConversation((prev) => ({
            ...prev,
            title: titleResponse.title,
          }));
        }

        await loadConversations();
      }

      setIsTyping(true);
      setIsStreaming(true);

      let assistantCreated = false;
      const assistantId = crypto.randomUUID();
      let assistantResponse = "";

      // Stream AI response
      await streamMessage(
        conversationContext,
        (chunk) => {
          assistantResponse += chunk;

          // First chunk received
          if (!assistantCreated) {
            assistantCreated = true;

            // Remove "AskLaw is thinking..."
            setIsTyping(false);

            setConversation((prev) => ({
              ...prev,
              messages: [
                ...prev.messages,
                {
                  id: assistantId,
                  role: "assistant",
                  content: assistantResponse,
                  isComplete: false,
                },
              ],
            }));

            return;
          }

          // Update assistant message while streaming
          setConversation((prev) => ({
            ...prev,
            messages: prev.messages.map((msg) =>
              msg.id === assistantId
                ? {
                  ...msg,
                  content: assistantResponse,
                }
                : msg
            ),
          }));
        }
      );

      // Mark assistant response as complete
      setConversation((prev) => ({
        ...prev,
        messages: prev.messages.map((msg) =>
          msg.id === assistantId
            ? {
              ...msg,
              isComplete: true,
            }
            : msg
        ),
      }));

      // Save completed AI response to MongoDB
      if (assistantResponse) {
        await addMessage(
          conversationId,
          "assistant",
          assistantResponse
        );
      }

      // Refresh sidebar conversation list
      await loadConversations();
    } catch (error) {
      if (error.name !== "AbortError") {
        console.error(error);

        setConversation((prev) => ({
          ...prev,
          messages: [
            ...prev.messages,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "Sorry, something went wrong.",
              isComplete: true,
            },
          ],
        }));
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

  // Create a brand-new conversation
  const createConversation = async () => {
    stopStreaming();

    setIsTyping(false);
    setIsStreaming(false);

    try {
      const newConversation =
        await createConversationApi();

      setConversation({
        id: newConversation.id,
        title: newConversation.title,
        messages: newConversation.messages,
      });

      // Refresh sidebar list
      await loadConversations();
    } catch (error) {
      console.error(
        "Failed to create conversation:",
        error
      );
    }
  };

  // Load one existing conversation
  const loadConversation = async (conversationId) => {
    stopStreaming();

    setIsTyping(false);
    setIsStreaming(false);

    try {
      const loadedConversation =
        await getConversation(conversationId);

      if (!loadedConversation?.id) {
        console.error("Conversation not found");
        return;
      }

      const loadedMessages =
        loadedConversation.messages.map(
          (message) => ({
            ...message,
            id:
              message.id ||
              crypto.randomUUID(),
            isComplete: true,
          })
        );

      setConversation({
        id: loadedConversation.id,
        title: loadedConversation.title,
        messages: loadedMessages,
      });
    } catch (error) {
      console.error(
        "Failed to load conversation:",
        error
      );
    }
  };

  return {
    conversation,
    conversations,
    messages: conversation.messages,

    isTyping,
    isStreaming,

    sendMessage,
    stop,
    createConversation,
    loadConversation,
  };
}