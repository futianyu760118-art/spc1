"""Work instruction document API."""

from app.api.v1.common.business_documents import create_business_document_router

router = create_business_document_router("work_instruction", "rules.work_instructions")
