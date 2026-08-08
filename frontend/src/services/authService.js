import api from "./api";

export const login = async (formData)=>{

    try{
        const response = await api.post("/auth/login",formData);

    return response.data;
    }

    catch(error){
        throw error;
    }
    
}

export const getCurrentUser = async () => {
    const response = await api.get("/auth/me");
    return response.data;
};

export const signup = async (formData) => {
  try {
    const response = await api.post("/auth/signup", formData);
    return response.data;
  } catch (error) {
    throw error;
  }
};

export const logout = async () => {
  const response = await api.post("/auth/logout");

  localStorage.removeItem("token");

  return response.data;
};

export const getMe = async () => {
  const response = await api.get("/auth/me");
  return response.data;
};

