from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.core.config import settings
from app.db.mongodb import user_collection

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
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
    print("TOKEN:", token)

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        print("PAYLOAD:", payload)

        email = payload.get("sub")
        print("EMAIL:", email)

        if email is None:
            print("No email in token")
            raise credentials_exception

        user = user_collection.find_one({
            "email": email
        })

        print("USER:", user)

        if user is None:
            print("User not found")
            raise credentials_exception

        return user

    except JWTError as e:
        print("JWT ERROR:", e)
        raise credentials_exception