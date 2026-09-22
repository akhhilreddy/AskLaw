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

        # Tokens issued before token_type was introduced remain valid during
        # migration. Newly issued refresh tokens cannot authenticate requests.
        if email is None or token_type not in {None, "access"}:
            raise credentials_exception

        user = user_collection.find_one({
            "email": email
        })

        if user is None:
            raise credentials_exception

        return user

    except JWTError:
        raise credentials_exception
