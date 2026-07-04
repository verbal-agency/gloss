from __future__ import annotations
import uuid
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from app.middleware import process
from app.models import (
    MessagesRequest, MessagesResponse,
    NormalizeRequest, CounterfactualRequest, PrecommitRequest,
    PressureTestRequest, InterrogateRequest, CheckDriftRequest,
)
from app.pipeline import adversarial, counterfactual, disagreement, normalizer, precommitment, temporal

app = FastAPI(title="Gloss", version="0.1.0")


# ---------------------------------------------------------------------------
# Full pipeline proxy — drop-in replacement for /v1/messages
# ---------------------------------------------------------------------------

@app.post("/v1/messages", response_model=MessagesResponse)
async def messages(
    request: MessagesRequest,
    x_session_id: str | None = Header(default=None),
):
    if request.stream:
        # Anthropic error envelope so SDK clients raise a proper BadRequestError
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        "Streaming is not supported: the detection pipeline must "
                        "score the complete response before returning it. Set stream=false."
                    ),
                },
            },
        )
    session_id = x_session_id or str(uuid.uuid4())
    return await process(request, session_id)


# ---------------------------------------------------------------------------
# Individual stage endpoints — composable agent tools
# ---------------------------------------------------------------------------

@app.post("/v1/normalize")
async def normalize(request: NormalizeRequest):
    result = await normalizer.run(request.query)
    return result.model_dump()


@app.post("/v1/counterfactual")
async def run_counterfactual(request: CounterfactualRequest):
    msgs = [m.model_dump() for m in request.messages]
    if not msgs:
        msgs = [{"role": "user", "content": request.query}]
    result = await counterfactual.run(request.query, msgs)
    if result is None:
        return {"flagged": False, "reason": "No opinion signal detected in query."}
    return result.model_dump()


@app.post("/v1/precommit")
async def run_precommit(
    request: PrecommitRequest,
    x_session_id: str | None = Header(default=None),
):
    session_id = x_session_id or request.session_id
    msgs = [m.model_dump() for m in request.messages]
    if not msgs:
        msgs = [{"role": "user", "content": request.query}]
    domain = precommitment.classify_domain(request.query)
    result = await precommitment.run(request.query, msgs, domain, session_id)
    return result.model_dump()


@app.post("/v1/pressure-test")
async def pressure_test(request: PressureTestRequest):
    msgs = [m.model_dump() for m in request.messages]
    result = await disagreement.run(request.response, msgs)
    return result.model_dump()


@app.post("/v1/interrogate")
async def interrogate(request: InterrogateRequest):
    domain = None if request.domain == "auto" else request.domain
    result = await adversarial.run(request.query, request.response, domain)
    return result.model_dump()


@app.post("/v1/check-drift")
async def check_drift(request: CheckDriftRequest):
    result = await temporal.check_arc(request.session_id, request.turn)
    if result is None:
        return {"flagged": False, "reason": "Insufficient turns or drift below threshold."}
    return result.model_dump()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
