from decimal import Decimal
from app.core.config import settings
from app.schemas.promotion_schema import PromotionCandidate, PromotionProcessingResult

class AmazonService:
  
    def fetch_promotions(self) -> list[PromotionCandidate]:
        candidates = [
          
            PromotionCandidate(
                asin="B0CNOTE001",
                title="Notebook Acer Aspire 5 Intel Core i5 16GB RAM 512GB SSD",
                original_price=Decimal("4299.90"),
                discounted_price=Decimal("3299.90"),
                discount_percentage=Decimal("23.26"),
                product_url="https://www.amazon.com.br/dp/B0CNOTE001",
                image_url="https://m.media-amazon.com/images/I/71mocknotebook.jpg",
                category="Computers",
                rating=Decimal("4.70"),
            ),
            
            PromotionCandidate(
                asin="B0CPHONE02",
                title="Smartphone Samsung Galaxy 256GB Tela AMOLED",
                original_price=Decimal("2599.90"),
                discounted_price=Decimal("1999.90"),
                discount_percentage=Decimal("23.08"),
                product_url="https://www.amazon.com.br/dp/B0CPHONE02",
                image_url="https://m.media-amazon.com/images/I/71mockphone.jpg",
                category="Electronics",
                rating=Decimal("4.60"),
            ),
            
            PromotionCandidate(
                asin="B0LOWDISC04",
                title="Mouse Sem Fio Compacto USB",
                original_price=Decimal("89.90"),
                discounted_price=Decimal("79.90"),
                discount_percentage=Decimal("11.12"),
                product_url="https://www.amazon.com.br/dp/B0LOWDISC04",
                image_url="https://m.media-amazon.com/images/I/51mockmouse.jpg",
                category="Computers",
                rating=Decimal("4.30"),
            ),  
        ]
      
        return [
            candidate
            for candidate in candidates
            if candidate.discount_percentage >= settings.amazon_min_discount_percent
        ]