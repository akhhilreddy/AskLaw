from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator


SignupName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
SignupPassword = Annotated[str, Field(min_length=8, max_length=72)]
LoginPassword = Annotated[str, Field(min_length=1, max_length=72)]


class PasswordByteLimitMixin:
    @field_validator("password")
    @classmethod
    def password_must_fit_bcrypt(cls, password: str) -> str:
        if len(password.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return password


class SignUpRequest(PasswordByteLimitMixin, BaseModel):
    name: SignupName
    email: EmailStr
    password: SignupPassword


class UserLogin(PasswordByteLimitMixin, BaseModel):
    email: EmailStr
    password: LoginPassword
