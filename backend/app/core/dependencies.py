from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.core.config import settings
from app.db.mongodb import user_collection


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token"
)


credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={
        "WWW-Authenticate": "Bearer"
    }
)


def get_current_user(
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        email = payload.get("sub")
        token_type = payload.get("token_type")

        # Protected endpoints accept access tokens only. Legacy untyped refresh
        # tokens may be accepted by /auth/refresh during migration, but they
        # must never double as bearer access tokens.
        if email is None or token_type != "access":
            raise credentials_exception

        user = user_collection.find_one({
            "email": email
        })

        if user is None:
            raise credentials_exception

        if user.get("email_verified") is False:
            raise credentials_exception

        user_auth_version = user.get("auth_version")
        if (
            user_auth_version is not None
            and payload.get("auth_version") != user_auth_version
        ):
            raise credentials_exception

        return user

    except JWTError:
        raise credentials_exception
