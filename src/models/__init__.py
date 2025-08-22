from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field


class ProductInfo(BaseModel):
    """Modelo para informações do produto extraídas"""

    name: str = Field(description="Nome do produto")
    price: Optional[float] = Field(default=None, description="Preço atual do produto")
    original_price: Optional[float] = Field(
        default=None, description="Preço original (sem desconto)"
    )
    discount_percentage: Optional[float] = Field(
        default=None, description="Percentual de desconto"
    )
    availability: str = Field(
        default="unknown", description="Status de disponibilidade"
    )
    url: HttpUrl = Field(description="URL do produto")
    site: str = Field(description="Nome do site de origem")
    image_url: Optional[HttpUrl] = Field(
        default=None, description="URL da imagem do produto"
    )
    description: Optional[str] = Field(default=None, description="Descrição do produto")
    rating: Optional[float] = Field(default=None, description="Avaliação do produto")
    reviews_count: Optional[int] = Field(
        default=None, description="Número de avaliações"
    )
    delivery_info: Optional[str] = Field(
        default=None, description="Informações de prazo de entrega"
    )
    scraped_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp do scraping"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ScrapingRequest(BaseModel):
    """Modelo para requisição de scraping"""

    product_name: str = Field(description="Nome do produto a ser buscado")
    target_sites: List[str] = Field(description="Lista de sites para buscar")
    max_results_per_site: int = Field(
        default=5, description="Máximo de resultados por site"
    )


class ScrapingResult(BaseModel):
    """Modelo para resultado completo do scraping"""

    request: ScrapingRequest
    products: List[ProductInfo] = Field(
        default=[], description="Lista de produtos encontrados"
    )
    errors: List[str] = Field(default=[], description="Lista de erros encontrados")
    total_found: int = Field(default=0, description="Total de produtos encontrados")
    execution_time: float = Field(description="Tempo de execução em segundos")
    scraped_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp do resultado"
    )

    def add_product(self, product: ProductInfo):
        """Adiciona um produto ao resultado"""
        self.products.append(product)
        self.total_found = len(self.products)

    def add_error(self, error: str):
        """Adiciona um erro ao resultado"""
        self.errors.append(error)


class SiteConfig(BaseModel):
    """Configuração específica de cada site"""

    name: str
    base_url: str
    search_url_pattern: str
    selectors: dict
    headers: Optional[dict] = None
    rate_limit_delay: float = 1.0
    max_retries: int = 3
