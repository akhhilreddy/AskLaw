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
  deleteConversation as deleteConversationApi,
  renameConversation as renameConversationApi,
} from "../services/conversationService";


export default function useChat() {

  const [conversation, setConversation] =
    useState({
      id: null,
      title: "New Chat",
      messages: [],
    });

  const [conversations, setConversations] =
    useState([]);

  const [isTyping, setIsTyping] =
    useState(false);

  const [isStreaming, setIsStreaming] =
    useState(false);


  // =====================================================
  // LOAD CONVERSATIONS
  // =====================================================

  const loadConversations = async () => {

    try {

      const data =
        await getConversations();

      setConversations(data);

    } catch (error) {

      console.error(
        "Failed to load conversations:",
        error
      );

    }

  };


  // =====================================================
  // INITIAL LOAD
  // =====================================================

  useEffect(() => {

    loadConversations();

  }, []);


  // =====================================================
  // SEND MESSAGE
  // =====================================================

  const sendMessage = async (
    message
  ) => {

    let conversationId =
      conversation.id;

    try {

      // -----------------------------------------------
      // Create conversation if needed
      // -----------------------------------------------

      if (!conversationId) {

        const newConversation =
          await createConversationApi();

        conversationId =
          newConversation.id;

        setConversation((prev) => ({
          ...prev,
          id: newConversation.id,
          title:
            newConversation.title ||
            "New Chat",
        }));

        await loadConversations();

      }


      // -----------------------------------------------
      // User message
      // -----------------------------------------------

      const userMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: message,
      };


      // -----------------------------------------------
      // Conversation context
      // -----------------------------------------------

      const conversationContext = [

        ...conversation.messages
          .slice(-12)
          .map(
            ({
              role,
              content,
            }) => ({
              role,
              content,
            })
          ),

        {
          role: "user",
          content: message,
        },

      ];


      // -----------------------------------------------
      // Update UI
      // -----------------------------------------------

      setConversation((prev) => ({
        ...prev,

        messages: [
          ...prev.messages,
          userMessage,
        ],

      }));


      // -----------------------------------------------
      // Save user message
      // -----------------------------------------------

      await addMessage(
        conversationId,
        "user",
        message
      );


      // -----------------------------------------------
      // Automatic title
      // -----------------------------------------------

      if (
        conversation.messages
          .length === 0
      ) {

        const titleResponse =
          await updateConversationTitle(
            conversationId
          );

        if (titleResponse?.title) {

          setConversation(
            (prev) => ({
              ...prev,

              title:
                titleResponse.title,

            })
          );

        }

        await loadConversations();

      }


      // -----------------------------------------------
      // Start streaming
      // -----------------------------------------------

      setIsTyping(true);

      setIsStreaming(true);


      // -----------------------------------------------
      // Assistant message state
      // -----------------------------------------------

      let assistantCreated =
        false;

      const assistantId =
        crypto.randomUUID();

      let assistantResponse =
        "";

      let assistantSources =
        [];


      // -----------------------------------------------
      // CREATE ASSISTANT MESSAGE
      // -----------------------------------------------

      const createAssistantMessage = () => {

        if (assistantCreated) {

          return;

        }

        assistantCreated =
          true;

        setIsTyping(false);

        setConversation(
          (prev) => ({
            ...prev,

            messages: [
              ...prev.messages,

              {
                id: assistantId,
                role: "assistant",
                content:
                  assistantResponse,
                sources:
                  assistantSources,
                isComplete: false,
              },

            ],

          })
        );

      };


      // -----------------------------------------------
      // UPDATE ASSISTANT MESSAGE
      // -----------------------------------------------

      const updateAssistantMessage = () => {

        setConversation(
          (prev) => ({
            ...prev,

            messages:
              prev.messages.map(
                (msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,

                        content:
                          assistantResponse,

                        sources:
                          assistantSources,
                      }
                    : msg
              ),

          })
        );

      };


      // -----------------------------------------------
      // STREAM RESPONSE
      // -----------------------------------------------

      await streamMessage(
        conversationContext,

        (event) => {

          // -------------------------------------------
          // TOKEN EVENT
          // -------------------------------------------

          if (
            event.type === "token"
          ) {

            assistantResponse +=
              event.content;

            createAssistantMessage();

            updateAssistantMessage();

            return;

          }


          // -------------------------------------------
          // SOURCES EVENT
          // -------------------------------------------

          if (
            event.type === "sources"
          ) {

            assistantSources =
              event.sources || [];

            createAssistantMessage();

            updateAssistantMessage();

            return;

          }


          // -------------------------------------------
          // ERROR EVENT
          // -------------------------------------------

          if (
            event.type === "error"
          ) {

            assistantResponse +=
              event.content;

            createAssistantMessage();

            updateAssistantMessage();

          }

        }

      );


      // -----------------------------------------------
      // Mark complete
      // -----------------------------------------------

      if (assistantCreated) {

        setConversation(
          (prev) => ({
            ...prev,

            messages:
              prev.messages.map(
                (msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,

                        isComplete: true,
                      }
                    : msg
              ),

          })
        );

      }


      // -----------------------------------------------
      // Save assistant response
      // -----------------------------------------------

      if (assistantResponse) {

        await addMessage(
          conversationId,
          "assistant",
          assistantResponse
        );

      }


      await loadConversations();


    } catch (error) {

      if (
        error.name !==
        "AbortError"
      ) {

        console.error(
          "Failed to send message:",
          error
        );

        setConversation(
          (prev) => ({
            ...prev,

            messages: [
              ...prev.messages,

              {
                id:
                  crypto.randomUUID(),

                role: "assistant",

                content:
                  "Sorry, something went wrong.",

                sources: [],

                isComplete: true,
              },

            ],

          })
        );

      }

    } finally {

      setIsTyping(false);

      setIsStreaming(false);

    }

  };


  // =====================================================
  // STOP
  // =====================================================

  const stop = () => {

    stopStreaming();

    setIsTyping(false);

    setIsStreaming(false);

  };


  // =====================================================
  // NEW CONVERSATION
  // =====================================================

  const createConversation =
    async () => {

      stopStreaming();

      setIsTyping(false);

      setIsStreaming(false);

      try {

        const newConversation =
          await createConversationApi();

        setConversation({
          id: newConversation.id,

          title:
            newConversation.title ||
            "New Chat",

          messages:
            newConversation.messages ||
            [],
        });

        await loadConversations();

      } catch (error) {

        console.error(
          "Failed to create conversation:",
          error
        );

      }

    };


  // =====================================================
  // LOAD CONVERSATION
  // =====================================================

  const loadConversation = async (
    conversationId
  ) => {

    stopStreaming();

    setIsTyping(false);

    setIsStreaming(false);

    try {

      const loadedConversation =
        await getConversation(
          conversationId
        );

      if (
        !loadedConversation?.id
      ) {

        console.error(
          "Conversation not found"
        );

        return;

      }

      const loadedMessages =
        (
          loadedConversation.messages ||
          []
        ).map((message) => ({
          ...message,

          id:
            message.id ||
            crypto.randomUUID(),

          sources:
            message.sources || [],

          isComplete: true,
        }));

      setConversation({

        id:
          loadedConversation.id,

        title:
          loadedConversation.title ||
          "New Chat",

        messages:
          loadedMessages,

      });

    } catch (error) {

      console.error(
        "Failed to load conversation:",
        error
      );

    }

  };


  // =====================================================
  // DELETE
  // =====================================================

  const deleteConversation =
    async (conversationId) => {

      try {

        await deleteConversationApi(
          conversationId
        );

        setConversations(
          (prev) =>
            prev.filter(
              (item) =>
                item.id !==
                conversationId
            )
        );

        if (
          conversation.id ===
          conversationId
        ) {

          stopStreaming();

          setIsTyping(false);

          setIsStreaming(false);

          setConversation({
            id: null,
            title: "New Chat",
            messages: [],
          });

        }

      } catch (error) {

        console.error(
          "Failed to delete conversation:",
          error
        );

        throw error;

      }

    };


  // =====================================================
  // RENAME
  // =====================================================

  const renameConversation =
    async (
      conversationId,
      title
    ) => {

      try {

        const result =
          await renameConversationApi(
            conversationId,
            title
          );

        const newTitle =
          result?.title ||
          title.trim();


        // Update sidebar

        setConversations(
          (prev) =>
            prev.map(
              (item) =>
                item.id ===
                conversationId
                  ? {
                      ...item,

                      title:
                        newTitle,
                    }
                  : item
            )
        );


        // Update active conversation

        setConversation(
          (prev) =>
            prev.id ===
            conversationId
              ? {
                  ...prev,

                  title:
                    newTitle,
                }
              : prev
        );

      } catch (error) {

        console.error(
          "Failed to rename conversation:",
          error.response
            ?.data || error
        );

        throw error;

      }

    };


  // =====================================================
  // RETURN
  // =====================================================

  return {

    conversation,

    conversations,

    messages:
      conversation.messages,

    isTyping,

    isStreaming,

    sendMessage,

    stop,

    createConversation,

    loadConversation,

    deleteConversation,

    renameConversation,

  };

}