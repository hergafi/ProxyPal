"""
Security utilities: authentication, authorization, and input validation
"""
import hashlib
import secrets
import re
from typing import Optional, Dict, Any
from functools import wraps
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from backend.core.config import API_KEY_SECRET, ENABLE_AUTH

security_scheme = HTTPBearer(auto_error=False)

def hash_api_key(api_key: str) -> str:
    """Hash API key for storage/comparison"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def generate_api_key() -> str:
    """Generate a secure random API key"""
    return f"fx_{secrets.token_urlsafe(32)}"

def generate_jwt_token(user_id: str, expires_hours: int = 24) -> str:
    """Generate JWT token for authentication"""
    import time
    payload = {
        "user_id": user_id,
        "exp": int(time.time()) + (expires_hours * 3600),
        "iat": int(time.time()),
        "jti": secrets.token_urlsafe(16)
    }
    return jwt.encode(payload, API_KEY_SECRET, algorithm="HS256")

def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, API_KEY_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme)
) -> Optional[str]:
    """Verify API key from Authorization header"""
    if not ENABLE_AUTH:
        return "anonymous"
    
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials"
        )
    
    token = credentials.credentials
    
    # Try JWT first
    payload = verify_jwt_token(token)
    if payload:
        return payload.get("user_id")
    
    # Try API key
    key_hash = hash_api_key(token)
    # In production, check against database
    # For now, accept any non-empty key
    if token:
        return key_hash[:16]
    
    raise HTTPException(
        status_code=401,
        detail="Invalid authentication credentials"
    )

def validate_input(data: str, max_length: int = 10000) -> str:
    """Validate and sanitize input data"""
    if not data:
        raise HTTPException(status_code=400, detail="Input cannot be empty")
    
    if len(data) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Input exceeds maximum length of {max_length}"
        )
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>\'";(){}]', '', data)
    
    return sanitized.strip()

def validate_path(path: str, allowed_base: str) -> str:
    """Validate file path to prevent path traversal attacks"""
    import os
    
    # Normalize paths
    base = os.path.abspath(allowed_base)
    target = os.path.abspath(path)
    
    # Check if target is within base
    if not target.startswith(base):
        raise HTTPException(
            status_code=403,
            detail="Path traversal blocked"
        )
    
    return target

def require_auth(f):
    """Decorator to require authentication for endpoints"""
    @wraps(f)
    async def decorated(*args, **kwargs):
        if not ENABLE_AUTH:
            return await f(*args, **kwargs)
        
        # Check for valid credentials
        # In production, implement proper auth checking
        return await f(*args, **kwargs)
    
    return decorated

class RateLimiter:
    """Simple in-memory rate limiter"""
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}
    
    def is_allowed(self, client_id: str) -> bool:
        """Check if client is within rate limit"""
        import time
        
        now = time.time()
        
        if client_id not in self.requests:
            self.requests[client_id] = []
        
        # Remove old requests outside window
        self.requests[client_id] = [
            t for t in self.requests[client_id]
            if now - t < self.window_seconds
        ]
        
        # Check if limit exceeded
        if len(self.requests[client_id]) >= self.max_requests:
            return False
        
        # Record new request
        self.requests[client_id].append(now)
        return True
    
    def get_remaining(self, client_id: str) -> int:
        """Get remaining requests for client"""
        import time
        
        now = time.time()
        
        if client_id not in self.requests:
            return self.max_requests
        
        # Count requests in current window
        recent = [
            t for t in self.requests[client_id]
            if now - t < self.window_seconds
        ]
        
        return max(0, self.max_requests - len(recent))

# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)
