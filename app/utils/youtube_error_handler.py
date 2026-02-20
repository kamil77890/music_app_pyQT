from googleapiclient.errors import HttpError
from app.exceptions.youtube_errors import (
    YouTubeQuotaExceededError,
    YouTubeAccessDeniedError,
    YouTubeNotFoundError,
    YouTubeBadRequestError,
    YouTubeServerError,
    YouTubeAPIError
)
from app.utils.api_key_manager import api_key_manager


def handle_youtube_api_error(error: HttpError) -> None:
    """
    Convert Google API HttpError to our custom YouTube errors
    """
    status_code = error.resp.status
    error_content = error.content.decode(
        'utf-8') if error.content else str(error)

    if status_code == 403:
        if "quotaExceeded" in error_content:
            # Check if we can switch to another key
            if api_key_manager.has_more_keys():
                # Switch key and indicate we should retry
                api_key_manager.switch_to_next_key()
                return  # Return instead of raising to allow retry
            else:
                raise YouTubeQuotaExceededError(error)
        else:
            raise YouTubeAccessDeniedError(error)

    elif status_code == 404:
        raise YouTubeNotFoundError("Requested resource", error)

    elif status_code == 400:
        raise YouTubeBadRequestError("Bad request parameters", error)

    elif status_code >= 500:
        raise YouTubeServerError(error)

    else:
        raise YouTubeAPIError(
            f"YouTube API error {status_code}: {error_content}", error)


def youtube_api_error_handler(func):
    """
    Decorator to handle YouTube API errors automatically with retry logic
    """
    def wrapper(*args, **kwargs):
        max_retries = len(api_key_manager.keys)
        retry_count = 0

        while retry_count <= max_retries:
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                retry_count += 1
                try:
                    # This will switch keys for quota errors and return (not raise)
                    handle_youtube_api_error(e)
                    # If we get here, it means we switched keys and should retry
                    print(
                        f"🔄 Retrying with new API key (attempt {retry_count}/{max_retries})")
                    continue
                except YouTubeAPIError as custom_error:
                    # If we get a custom error, raise it
                    if retry_count > max_retries:
                        raise custom_error
                    else:
                        # For non-quota errors, we might still want to retry with same key
                        print(
                            f"❌ API error (attempt {retry_count}/{max_retries}): {custom_error}")
                        if retry_count <= max_retries:
                            continue
                        raise

            except Exception as e:
                if retry_count > max_retries:
                    raise YouTubeAPIError(
                        f"Unexpected error after {max_retries} retries: {e}", e)
                else:
                    print(
                        f"⚠️ Unexpected error (attempt {retry_count}/{max_retries}): {e}")
                    continue

        raise YouTubeAPIError(f"Max retries ({max_retries}) exceeded")

    return wrapper
