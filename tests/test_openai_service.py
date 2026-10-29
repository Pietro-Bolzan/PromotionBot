from unittest.mock import MagicMock

from app.services.openai_service import OpenAIService


def test_prompt_does_not_give_the_product_url_to_the_llm(make_promotion):
    service = OpenAIService()
    service.client = MagicMock()
    service.client.responses.create.return_value.output_text = "Copy"

    service.generate_sales_copy(make_promotion())

    prompt = service.client.responses.create.call_args.kwargs["input"]
    assert "amazon.com.br" not in prompt


def test_fallback_copy_has_no_link(make_promotion):
    service = OpenAIService()
    assert service.client is None  # tests run without an OpenAI key

    assert "http" not in service.generate_sales_copy(make_promotion())
