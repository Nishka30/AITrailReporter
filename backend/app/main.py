from fastapi import FastAPI

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

app = FastAPI(title="AI Trail Reporter API")

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
