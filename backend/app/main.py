from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.extractions import router as extractions_router
from app.api.routes.geographic_context import router as geographic_context_router
from app.api.routes.guide_locations import router as guide_locations_router
from app.api.routes.guides import router as guides_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge_decisions import router as knowledge_decisions_router
from app.api.routes.knowledge_state import router as knowledge_state_router
from app.api.routes.locations import router as locations_router
from app.api.routes.questions import router as questions_router
from app.api.routes.submissions import router as submissions_router
from app.api.routes.transcriptions import router as transcriptions_router
from app.core.config import settings

app = FastAPI(title="AI Trail Reporter API")

# Only the admin web app needs CORS -- the mobile app's requests were never
# subject to it (React Native `fetch` is not a browser). Scoped to the
# configured admin origins only (see settings.admin_cors_origins); never "*",
# since /api/v1/admin/* returns contributor phone numbers and other data that
# must not be reachable from an arbitrary origin. Headers/methods are left
# permissive within that origin restriction since the admin API uses custom
# headers (X-Admin-Token, X-Admin-Name) and several HTTP methods.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.admin_cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(guides_router)
app.include_router(guide_locations_router)
app.include_router(locations_router)
app.include_router(geographic_context_router)
app.include_router(submissions_router)
app.include_router(transcriptions_router)
app.include_router(extractions_router)
app.include_router(knowledge_state_router)
app.include_router(knowledge_decisions_router)
app.include_router(questions_router)
app.include_router(admin_router)
