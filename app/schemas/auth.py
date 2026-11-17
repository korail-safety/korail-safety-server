from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints

from app.schemas.base import CamelModel

LoginId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=20)]


class SignupRequest(CamelModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    admin_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    email: EmailStr
    id: LoginId
    password: str = Field(min_length=8, max_length=72)  # bcrypt는 72바이트까지만 쓴다


class LoginRequest(CamelModel):
    id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    password: str = Field(min_length=1)


class MeResponse(CamelModel):
    """로그인한 사용자. id는 로그인 아이디(login_id)"""

    id: str
    name: str


class CheckIdResponse(CamelModel):
    available: bool
