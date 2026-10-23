import logging
import re

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.core.config import (
    OPENAI_API_KEY,
    OPENAI_MAX_RETRIES,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class ChatAIConfigurationError(Exception):
    pass


class ChatAIUnavailableError(Exception):
    pass


def chat_ai_is_configured() -> bool:
    return bool(OPENAI_API_KEY.strip() and OPENAI_MODEL.strip())


def _provider_error_code(error: APIStatusError) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code):
        return code
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        error_body = body.get("error")
        body_code = error_body.get("code") if isinstance(error_body, dict) else None
        if isinstance(body_code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", body_code):
            return body_code
    return "unavailable"


def _safe_error(error: APIStatusError) -> ChatAIUnavailableError:
    status_code = error.status_code
    code = _provider_error_code(error)
    logger.error(
        "OpenAI API request failed: http_status=%s error_code=%s exception_type=%s",
        status_code,
        code,
        type(error).__name__,
    )

    if isinstance(error, AuthenticationError) or status_code == 401:
        detail = "The RentTrace AI service is currently unavailable. Please try again later."
    elif isinstance(error, PermissionDeniedError) or status_code == 403:
        detail = "The RentTrace AI service is not permitted to process this request. Please try again later."
    elif isinstance(error, RateLimitError) or status_code == 429:
        if code == "insufficient_quota":
            detail = (
                "The RentTrace AI service has reached its API usage limit. "
                "Please try again later."
            )
        else:
            detail = (
                "The RentTrace AI service is receiving too many requests. "
                "Please wait a moment and try again."
            )
    elif isinstance(error, NotFoundError) or status_code == 404:
        detail = (
            "The configured OpenAI model is unavailable to this account. "
            "Check OPENAI_MODEL and the models enabled for your API account."
        )
    elif isinstance(error, BadRequestError) or status_code == 400:
        detail = "RentTrace AI could not process this request. Please try a shorter or clearer question."
    elif status_code >= 500:
        detail = "RentTrace AI is temporarily unavailable. Please try again later."
    else:
        detail = "RentTrace AI could not complete that request. Please try again later."
    return ChatAIUnavailableError(detail)


async def generate_chat_completion(messages: list[dict[str, str]]) -> str:
    if not chat_ai_is_configured():
        raise ChatAIConfigurationError(
            "RentTrace AI needs OPENAI_API_KEY in the project-root .env and an OPENAI_MODEL accessible to the account."
        )

    instructions = "\n\n".join(
        message["content"] for message in messages if message["role"] == "system"
    )
    input_messages = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] != "system"
    ]
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        timeout=OPENAI_TIMEOUT_SECONDS,
        max_retries=OPENAI_MAX_RETRIES,
    )
    try:
        logger.info("Sending RentTrace chat request to OpenAI Responses API.")
        response = await client.responses.create(
            model=OPENAI_MODEL,
            instructions=instructions,
            input=input_messages,
        )
        output = response.output_text
    except RateLimitError as exc:
        raise _safe_error(exc) from exc
    except AuthenticationError as exc:
        raise _safe_error(exc) from exc
    except PermissionDeniedError as exc:
        raise _safe_error(exc) from exc
    except NotFoundError as exc:
        raise _safe_error(exc) from exc
    except BadRequestError as exc:
        raise _safe_error(exc) from exc
    except APITimeoutError as exc:
        logger.error(
            "OpenAI API request timed out: timeout_seconds=%s exception_type=%s",
            OPENAI_TIMEOUT_SECONDS,
            type(exc).__name__,
        )
        raise ChatAIUnavailableError(
            "The RentTrace AI request timed out. Please try again."
        ) from exc
    except APIConnectionError as exc:
        logger.error(
            "OpenAI API connection failed: exception_type=%s",
            type(exc).__name__,
        )
        raise ChatAIUnavailableError(
            "RentTrace AI could not connect to its provider. Check the backend network and try again."
        ) from exc
    except APIStatusError as exc:
        raise _safe_error(exc) from exc
    finally:
        await client.close()

    if not isinstance(output, str) or not output.strip():
        logger.warning("OpenAI Responses API returned an empty text response.")
        raise ChatAIUnavailableError(
            "RentTrace AI did not receive a usable response. Please try again."
        )
    logger.info("OpenAI Responses API returned a chat response.")
    return output.strip()
