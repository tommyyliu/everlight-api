import logging

import firebase_admin
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from sqlalchemy.orm import Session

from db.models import User
from db.session import get_db_session

if not firebase_admin._apps:
    firebase_app = firebase_admin.initialize_app()
else:
    firebase_app = firebase_admin.get_app()

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Security(HTTPBearer(auto_error=True)),
        db: Session = Depends(get_db_session)
) -> User:
    """
    Verifies Firebase ID Token from Authorization header and returns user claims.
    FastAPI handles providing the credentials object.
    """
    id_token = credentials.credentials

    try:
        claims = auth.verify_id_token(id_token)
        # Fetch user with this uid from the database
        user = db.query(User).filter(User.firebase_user_id == claims["user_id"]).first()
        if user:
            return user
        else:
            # Create a new user if they don't exist in the database
            new_user = User(firebase_user_id=claims["user_id"], email=claims["email"])
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            # Note: Default agents creation removed since it's not available in everlight-api
            return new_user
    except auth.ExpiredIdTokenError as e:
        logging.warning(f"Expired Firebase ID token: {e}")
        raise HTTPException(status_code=401, detail="Expired Firebase ID token, please reauthenticate")
    except auth.RevokedIdTokenError as e:
        logging.warning(f"Revoked Firebase ID token: {e}")
        raise HTTPException(status_code=401, detail="Firebase ID token has been revoked")
    except auth.InvalidIdTokenError as e:
        logging.warning(f"Invalid Firebase ID token: {e}")
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token")
    except ValueError as e:
        logging.warning(f"ValueError: {e}")
        raise HTTPException(status_code=401, detail="Token was not a string or was empty.")
    except Exception as e:
        logging.exception(f"An unexpected error occurred during token verification: {e}")
        raise HTTPException(status_code=500, detail="Could not process authentication token")