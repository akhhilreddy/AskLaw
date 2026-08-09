import api from "./api";

// -----------------------------------------
// Create conversation
// -----------------------------------------

export const createConversation = async () => {
  const response = await api.post("/conversations");

  return response.data;
};

// -----------------------------------------
// Get all conversations
// -----------------------------------------

export const getConversations = async () => {
  const response = await api.get("/conversations");

  return response.data;
};

// -----------------------------------------
// Get single conversation
// -----------------------------------------

export const getConversation = async (
  conversationId
) => {
  const response = await api.get(
    `/conversations/${conversationId}`
  );

  return response.data;
};

// -----------------------------------------
// Add message
// -----------------------------------------

export const addMessage = async (
  conversationId,
  role,
  content
) => {
  const response = await api.post(
    `/conversations/${conversationId}/messages`,
    {
      role,
      content,
    }
  );

  return response.data;
};

// -----------------------------------------
// Update automatic title
// -----------------------------------------

export const updateConversationTitle = async (
  conversationId
) => {
  const response = await api.patch(
    `/conversations/${conversationId}/title`
  );

  return response.data;
};

// -----------------------------------------
// Delete conversation
// -----------------------------------------

export const deleteConversation = async (
  conversationId
) => {
  const response = await api.delete(
    `/conversations/${conversationId}`
  );

  return response.data;
};

// -----------------------------------------
// Rename conversation
// -----------------------------------------

export const renameConversation = async (
  conversationId,
  title
) => {
  const response = await api.patch(
    `/conversations/${conversationId}/rename`,
    null,
    {
      params: {
        title,
      },
    }
  );

  return response.data;
};

