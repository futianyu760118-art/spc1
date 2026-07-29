from app.api.v1.basicdata.auth import router as auth_router
from app.api.v1.basicdata.users import router as users_router
from app.api.v1.basicdata.audit import router as audit_router
from app.api.v1.basicdata.import_export import router as import_export_router
from app.api.v1.basicdata.sync import router as sync_router
from app.api.v1.basicdata.sync_sql import router as sync_sql_router
from app.api.v1.basicdata.basicdata import router as basicdata_router
from app.api.v1.basicdata.subject_balance import router as subject_balance_router
from app.api.v1.basicdata.feedback import router as feedback_router
from app.api.v1.basicdata.announcements import router as announcements_router
from app.api.v1.basicdata.notifications import router as notifications_router
from app.api.v1.basicdata.share import router as share_router
from app.api.v1.basicdata.permissions import router as permissions_router
from app.api.v1.basicdata.data_supply import router as data_supply_router

masterdata_router = basicdata_router
