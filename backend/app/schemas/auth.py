from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=120)


class LoginOut(BaseModel):
    authenticated: bool = True
    expires_at: str
    user: dict


class MeOut(BaseModel):
    authenticated: bool
    user: dict | None = None
