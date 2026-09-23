if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("manual integration script")

from app.services.vector_service import (
    create_collection,
)


create_collection()

print(
    "AskLaw Qdrant collection created successfully."
)
