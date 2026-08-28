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
from app.api.routes.public import router as public_router
from app.api.routes.questions import router as questions_router
from app.api.routes.submissions import router as submissions_router
from app.api.routes.transcriptions import router as transcriptions_router
from app.core.config import settings

app = FastAPI(title="AI Trail Reporter API")

# The admin web app and the public traveller website are the only two
# browser clients of this API (the mobile app's requests were never subject
# to CORS -- React Native `fetch` is not a browser). Their allowed origins
# are configured and unioned here, but they remain conceptually separate
# settings (admin_cors_origins vs public_cors_origins): CORS only controls
# which browser origins may READ a response, it grants no additional access
# -- /api/v1/admin/* still requires require_admin's token regardless of
# origin, so allowing the public site's origin here does not expose
# phone numbers or unmoderated content to it. Never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.admin_cors_origin_list + settings.public_cors_origin_list,
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
app.include_router(public_router)
