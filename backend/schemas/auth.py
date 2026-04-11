from pydantic import BaseModel, Field


class AuthUserResponse(BaseModel):
    id: int
    email: str
    is_active: bool


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetRequestPayload(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class PasswordResetConfirmPayload(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)


class AuthResponse(BaseModel):
    user: AuthUserResponse
    message: str
