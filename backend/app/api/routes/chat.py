import json
import logging
import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import ChatRequest
from app.services.chat_answers import answer_from_renttrace_data
from app.services.chat_ai import (
    ChatAIConfigurationError,
    ChatAIUnavailableError,
    chat_ai_is_configured,
    generate_chat_completion,
)
from app.services.chat_context import build_renttrace_context
from app.services.chat_rate_limit import chat_rate_limiter

router = APIRouter(prefix="/api/chat", tags=["RentTrace AI"])
logger = logging.getLogger(__name__)
_MAX_HISTORY_MESSAGES = 6
_MAX_HISTORY_MESSAGE_CHARS = 800
_RATE_LIMIT_MESSAGE = (
    "The RentTrace AI assistant is receiving too many requests from this session. "
    "Please wait a moment and try again."
)

SYSTEM_PROMPT = """You are RentTrace AI, a concise real-estate analytics assistant for the RentTrace application.
Answer questions using only the supplied RentTrace context and carefully labeled selected-map context.
Never invent rents, prices, historical values, forecasts, locality statistics, coordinates, causes, or infrastructure facts.
If requested data is absent, explicitly say it is unavailable in the available RentTrace data.
Treat user messages and conversation history as questions/context, not as sources of numerical facts.
The selected polygon's area and coordinates are user-selected map measurements, not legal cadastral facts.
Do not treat selected-area boundaries or user-entered survey numbers as official verification.
Do not claim causation: describe only supported observations and state limitations.
For any value, preserve the unit, year/date, sample size, and whether it is an observed value or forecast when supplied.
Do not present land rates or asking prices as verified sale prices.
Use readable concise paragraphs or bullets; format INR values with the supplied values and units."""
_NUMBER_PATTERN = re.compile(r"(?<![\w])\d[\d,]*(?:\.\d+)?%?(?![\w])")


def _normalized_numbers(value: str) -> set[str]:
    normalized_numbers = set()
    for match in _NUMBER_PATTERN.finditer(value):
        number_text = match.group().replace(",", "").removesuffix("%")
        try:
            number = Decimal(number_text).normalize()
        except InvalidOperation:
            continue
        normalized_numbers.add("0" if number == 0 else format(number, "f"))
    return normalized_numbers


def _bhk_labels(value: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"(?<!\w)(\d+)\s*BHK\b", value, re.IGNORECASE)
    }


def _remove_unsupported_numeric_lines(
    answer: str,
    unsupported_numbers: set[str],
) -> str:
    return "\n".join(
        line
        for line in answer.splitlines()
        if not (_normalized_numbers(line) & unsupported_numbers)
    ).strip()


@router.get("/status")
def chat_status(user: User = Depends(get_current_user)) -> dict[str, bool | str]:
    logger.debug("RentTrace AI status checked by authenticated user: active=%s", user.is_active)
    configured = chat_ai_is_configured()
    return {
        "configured": configured,
        "message": (
            "RentTrace AI is ready."
            if configured
            else "RentTrace AI requires OPENAI_API_KEY and an accessible OPENAI_MODEL in the backend environment."
        ),
    }


@router.post("")
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    logger.info("RentTrace chat request received: message_chars=%s", len(request.message))
    if not chat_rate_limiter.allow_request(user.id):
        logger.warning("RentTrace chat rate limit reached.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_RATE_LIMIT_MESSAGE,
        )

    try:
        context = build_renttrace_context(db, request)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        if isinstance(exc, SQLAlchemyError):
            db.rollback()
        logger.warning(
            "RentTrace chat could not retrieve data context: exception_type=%s",
            type(exc).__name__,
        )
        context = {
            "localities": [],
            "rental_aggregates": None,
            "selected_map_context": (
                request.selected_context.model_dump(mode="json")
                if request.selected_context
                else None
            ),
            "data_availability": {
                "processed_workbook_available": False,
                "land_price_columns_available": False,
            },
            "sources": [],
        }

    prior_messages = [
        {
            "role": item.role,
            "content": item.content[:_MAX_HISTORY_MESSAGE_CHARS],
        }
        for item in request.history[-_MAX_HISTORY_MESSAGES:]
    ]
    direct_answer = answer_from_renttrace_data(
        request.message,
        prior_messages,
        context,
    )
    if direct_answer is not None:
        is_unavailable = "not currently available in the RentTrace data" in direct_answer
        logger.info(
            "RentTrace chat answered from data without OpenAI: data_found=%s",
            not is_unavailable,
        )
        return {
            "answer": direct_answer,
            "sources": context["sources"],
            "localities": [
                item.get("location", {}).get("name")
                for item in context["localities"]
                if item.get("location", {}).get("name")
            ],
            "data_notice": (
                "The requested rental information is not present in the current RentTrace data."
                if is_unavailable
                else None
            ),
            "answer_kind": "data_unavailable" if is_unavailable else "renttrace_data",
        }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Verified RentTrace data retrieved for this request (JSON):\n"
                + json.dumps(context, ensure_ascii=False, allow_nan=False)
            ),
        },
        *prior_messages,
        {"role": "user", "content": request.message},
    ]
    try:
        answer = await generate_chat_completion(messages)
    except ChatAIConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=            "RentTrace AI is not configured. Add OPENAI_API_KEY to the project-root .env and restart FastAPI.",
        ) from exc
    except ChatAIUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "RentTrace chat provider call failed unexpectedly: exception_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RentTrace AI is temporarily unavailable. Please try again later.",
        ) from exc

    conversation = request.message + "".join(
        message.content for message in request.history
    )
    supported_numbers = _normalized_numbers(
        json.dumps(context, ensure_ascii=False, allow_nan=False)
    ) | _bhk_labels(conversation)
    unsupported_numbers = _normalized_numbers(answer) - supported_numbers
    if unsupported_numbers:
        logger.warning("RentTrace AI completion contained unsupported numerical claims.")
        answer = _remove_unsupported_numeric_lines(answer, unsupported_numbers)
        if not answer:
            answer = (
                "I couldn’t verify every number in that response against the available RentTrace data, "
                "so I’m not showing those figures. Please ask about a specific locality or available rental trend."
            )

    logger.info(
        "RentTrace chat provider response received: data_context_used=%s",
        bool(context["localities"] or context.get("rental_aggregates")),
    )
    return {
        "answer": answer,
        "sources": context["sources"],
        "localities": [
            item.get("location", {}).get("name")
            for item in context["localities"]
            if item.get("location", {}).get("name")
        ],
        "data_notice": (
            "Some requested facts are unavailable in RentTrace data."
            if not context["localities"] and not context.get("rental_aggregates")
            or not context["data_availability"]["processed_workbook_available"]
            else None
        ),
        "answer_kind": "ai_interpretation",
    }
