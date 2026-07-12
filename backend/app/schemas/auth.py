from pydantic import BaseModel, EmailStr

class SignUpRequest(BaseModel):
    name : str
    email : EmailStr
    password : str