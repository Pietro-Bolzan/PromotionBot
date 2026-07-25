from openai import OpenAI
from app.core.config import settings
from app.models.promotions import Promotion


class OpenAIService:
    def __init__(self):
        self.client = None

        if settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def generate_sales_copy(self, promotion: Promotion) -> str:
        if self.client is None:
            return self._fallback_message(promotion)

        prompt = f"""
Crie uma mensagem de venda curta, direta e persuasiva em português brasileiro.

Produto: {promotion.title}
Preço original: R$ {promotion.original_price}
Preço com desconto: R$ {promotion.discounted_price}
Desconto: {promotion.discount_percentage}%
Categoria: {promotion.category}
Link: {promotion.product_url}

Regras:
- máximo 5 linhas
- destaque a economia
- gere urgência
- termine com o link
"""

        response = self.client.responses.create(
            model=settings.openai_model,
            instructions=(
                "Você é um copywriter especialista em vendas para WhatsApp e Telegram. "
                "Escreva mensagens curtas, naturais e persuasivas para o público brasileiro."
            ),
            input=prompt,
            max_output_tokens=settings.openai_max_output_tokens,
        )

        return response.output_text.strip()

    def _fallback_message(self, promotion: Promotion) -> str:
        return (
            f"Oferta encontrada: {promotion.title}\n"
            f"De R$ {promotion.original_price} por R$ {promotion.discounted_price}\n"
            f"Desconto de {promotion.discount_percentage}%\n"
            f"Confira: {promotion.product_url}"
        )