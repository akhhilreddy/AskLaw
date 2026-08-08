import api from "./api";

export const createConversation = async () => {
  const response = await api.post("/conversations");

  return response.data;
};

export const getConversations = async () => {
  const response = await api.get("/conversations");

  return response.data;
};

export const getConversation = async (conversationId) => {
  const response = await api.get(
    `/conversations/${conversationId}`
  );

  return response.data;
};

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

export const updateConversationTitle = async (
  conversationId
) => {
  const response = await api.patch(
    `/conversations/${conversationId}/title`
  );

  return response.data;
};