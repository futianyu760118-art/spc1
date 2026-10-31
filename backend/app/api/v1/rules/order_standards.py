"""Order standard document API."""

from app.api.v1.common.business_documents import create_business_document_router

router = create_business_document_router("order_standard", "rules.order_standards")
