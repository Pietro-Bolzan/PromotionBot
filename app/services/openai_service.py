import logging

from openai import (
    APIConnectionError,
    APIStatusError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.core.config import settings
from app.core.security import describe_error
from app.models.promotions import Promotion
from app.services.formatting import format_brl, format_discount

logger = logging.getLogger(__name__)

# The SDK itself retries connection errors, timeouts, 429 and 5xx responses with
# exponential backoff (0.5 s up to 8 s, with jitter). Two retries means three
# attempts; another retry loop around it would multiply them.
MAX_RETRIES = 2

# Status codes that mean the request itself is wrong (bad key, no access to the
# model, unknown model, invalid parameters): retrying will not help.
CONFIGURATION_ERROR_STATUSES = {400, 401, 403, 404}

# A failed call already took up to three timeouts. After this many in a row,
# the template is used straight away until the pause is over.
BREAKER_FAILURE_THRESHOLD = 3
BREAKER_RESET_SECONDS = 300


def _is_service_trouble(error: Exception) -> bool:
    # Unreachable, overloaded or failing on its side; a rejected key or model
    # is a configuration problem, answered at once, and does not count.
    return isinstance(error, APIConnectionError | RateLimitError | InternalServerError)


class OpenAIService:
    def __init__(self, breaker: CircuitBreaker | None = None):
        self.client = None
        self._breaker = breaker or CircuitBreaker(
            "OpenAI",
            failure_threshold=BREAKER_FAILURE_THRESHOLD,
            reset_timeout=BREAKER_RESET_SECONDS,
        )

        if settings.openai_api_key:
            self.client = OpenAI(
                api_key=settings.openai_api_key,
                # The SDK default waits up to 600 s for a response: one stuck
                # call would hold a whole scheduler cycle.
                timeout=settings.openai_timeout_seconds,
                max_retries=MAX_RETRIES,
            )

    def generate_sales_copy(self, promotion: Promotion) -> str:
        if self.client is None:
            return self._fallback_message(promotion)

        prompt = f"""
Crie uma mensagem de venda curta, direta e persuasiva em português brasileiro.

Produto: {promotion.title}
Preço original: {format_brl(promotion.original_price)}
Preço com desconto: {format_brl(promotion.discounted_price)}
Desconto: {format_discount(promotion.discount_percentage)}
Categoria: {promotion.category}

Regras:
- máximo 5 linhas
- destaque a economia
- gere urgência
- não inclua links nem URLs: o link do produto é adicionado automaticamente ao final
"""

        client = self.client
        try:
            response = self._breaker.call(
                lambda: client.responses.create(
                    model=settings.openai_model,
                    instructions=(
                        "Você é um copywriter especialista em vendas para WhatsApp "
                        "e Telegram. Escreva mensagens curtas, naturais e "
                        "persuasivas para o público brasileiro."
                    ),
                    input=prompt,
                    max_output_tokens=settings.openai_max_output_tokens,
                ),
                is_failure=_is_service_trouble,
            )
        except CircuitOpenError:
            logger.info("OpenAI is paused after repeated failures; using the template")
            return self._fallback_message(promotion)
        except OpenAIError as error:
            # A promotion must not be lost because the copywriter is down: the
            # template is plainer but carries the same prices.
            is_configuration_error = (
                isinstance(error, APIStatusError)
                and error.status_code in CONFIGURATION_ERROR_STATUSES
            )
            logger.log(
                logging.ERROR if is_configuration_error else logging.WARNING,
                "Copy generation failed, using the template: %s",
                describe_error(error),
            )
            return self._fallback_message(promotion)

        copy = response.output_text.strip()

        # An incomplete response (cut by max_output_tokens, for instance) can be
        # empty or stop mid-sentence; neither should reach the group.
        if response.status != "completed" or not copy:
            logger.warning(
                "Copy generation returned an unusable response "
                "(status=%s, empty=%s), using the template",
                response.status,
                not copy,
            )
            return self._fallback_message(promotion)

        return copy

    def _fallback_message(self, promotion: Promotion) -> str:
        original = format_brl(promotion.original_price)
        discounted = format_brl(promotion.discounted_price)
        return (
            f"Oferta encontrada: {promotion.title}\n"
            f"De {original} por {discounted}\n"
            f"Desconto de {format_discount(promotion.discount_percentage)}"
        )
