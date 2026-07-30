"""
Domain-level exceptions for authentication.

Services raise these instead of `HTTPException` directly, which keeps the
service layer free of HTTP concerns. `app.middleware.error_handler`
registers handlers that translate each of these into the appropriate
HTTP status code and a consistent `{"detail": ...}` response body.
"""


class AppError(Exception):
    """Base class for all application-raised (as opposed to unexpected) errors."""

    status_code: int = 400
    detail: str = "An error occurred."

    def __init__(self, detail: str | None = None) -> None:
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class UserAlreadyExistsError(AppError):
    status_code = 409
    detail = "An account with this email already exists."


class InvalidCredentialsError(AppError):
    status_code = 401
    detail = "Incorrect email or password."


class InactiveUserError(AppError):
    status_code = 403
    detail = "This account is inactive."


class InvalidTokenError(AppError):
    status_code = 401
    detail = "Invalid or expired token."


class TokenRevokedError(AppError):
    status_code = 401
    detail = "This token has been revoked. Please log in again."


class UserNotFoundError(AppError):
    status_code = 404
    detail = "User not found."


class EmailProviderConflictError(AppError):
    status_code = 409
    detail = "This email is already registered with a different sign-in method."


class OAuthProviderError(AppError):
    status_code = 400
    detail = "Authentication with the identity provider failed."


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    detail = "Unsupported file type. Please upload a JPEG, PNG, or WebP image."


class PayloadTooLargeError(AppError):
    status_code = 413
    detail = "File is too large."


class InvalidImageError(AppError):
    status_code = 422
    detail = "This file doesn't look like a valid image."


class NotAuthenticatedError(AppError):
    status_code = 401
    detail = "Not authenticated."
