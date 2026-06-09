"""Product sample sealing document API."""

from app.api.v1.common.business_documents import create_business_document_router

router = create_business_document_router("product_sample", "exceptions.product_samples")
