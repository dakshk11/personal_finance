from fastapi import APIRouter

from app.schemas.common import IndexOut
from app.services.index_data import INDEX_DEFINITIONS


router = APIRouter(prefix="/indices", tags=["indices"])


@router.get("", response_model=list[IndexOut])
def list_indices() -> list[IndexOut]:
    return [
        IndexOut(
            symbol=definition.symbol,
            name=definition.name,
            provider=definition.provider,
            benchmark=definition.benchmark,
            inception_date=definition.inception_date,
            holdings_count=len(definition.holdings),
            source_url=definition.source_url,
        )
        for definition in INDEX_DEFINITIONS.values()
    ]

