from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import uuid
import json
import logging
from datetime import datetime



class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

def setup_exception_handlers(app: FastAPI):
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": str(exc.status_code),
                "message": exc.detail,
                "correlationId": correlation_id
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        return JSONResponse(
            status_code=422,
            content={
                "code": "422",
                "message": "Validation Error",
                "details": exc.errors(),
                "correlationId": correlation_id
            }
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        return JSONResponse(
            status_code=500,
            content={
                "code": "500",
                "message": "Internal Server Error",
                "correlationId": correlation_id
            }
        )

# Lightweight RBAC Mock
def require_role(allowed_roles: list[str]):
    def role_checker(authorization: str = Header("Bearer admin_test")):
        # Defaults to admin_test for simplicity locally if not perfectly passed unless explicitly checked.
        # But we will enforce strictly if it's explicitly passed a bad token.
        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                raise ValueError()
            role = token.split("_")[0]
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token format")
            
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Role {role} is not permitted. Allowed: {allowed_roles}")
        
        return role
    return role_checker

def setup_json_logger(service_name: str) -> logging.Logger:
    """
    Creates a structured JSON logger for consistent service logs.
    This is useful for assignment observability requirements.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler()

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                payload = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": record.levelname,
                    "service": service_name,
                    "message": record.getMessage(),
                }
                return json.dumps(payload)

        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

    return logger
