import bcrypt

def hash_password(password : str) -> str:
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes,salt)

    return hashed_password.decode("utf-8")
