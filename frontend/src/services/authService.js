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