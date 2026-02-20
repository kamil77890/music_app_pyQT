class YouTubeAPIError(Exception):
    """Base exception for YouTube API errors"""

    def __init__(self, message: str, original_error: Exception = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

    def __str__(self):
        if self.original_error:
            return f"{self.message} (Original: {self.original_error})"
        return self.message


class YouTubeQuotaExceededError(YouTubeAPIError):
    """Raised when YouTube API quota is exceeded"""

    def __init__(self, original_error: Exception = None):
        message = "YouTube API daily quota has been exceeded. Please try again tomorrow."
        super().__init__(message, original_error)


class YouTubeAccessDeniedError(YouTubeAPIError):
    """Raised when access to YouTube API is denied"""

    def __init__(self, original_error: Exception = None):
        message = "Access to YouTube API was denied. Please check your API key."
        super().__init__(message, original_error)


class YouTubeNotFoundError(YouTubeAPIError):
    """Raised when a resource is not found"""

    def __init__(self, resource: str, original_error: Exception = None):
        message = f"YouTube resource not found: {resource}"
        super().__init__(message, original_error)


class YouTubeBadRequestError(YouTubeAPIError):
    """Raised when the request is invalid"""

    def __init__(self, details: str, original_error: Exception = None):
        message = f"Invalid request to YouTube API: {details}"
        super().__init__(message, original_error)


class YouTubeServerError(YouTubeAPIError):
    """Raised when YouTube API server has issues"""

    def __init__(self, original_error: Exception = None):
        message = "YouTube API server is experiencing issues. Please try again later."
        super().__init__(message, original_error)
