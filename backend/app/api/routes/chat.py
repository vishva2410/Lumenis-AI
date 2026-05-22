"""
Lumenis AI — Chat Router (Phase 4)

Real-time streaming WebSocket endpoint for follow-up Q&A about a
completed analysis.  Retrieves relevant context from Qdrant on the
fly and streams Gemini responses token-by-token.

Protocol (JSON frames over WebSocket):
  Client → Server:  {"message": "What does pleural effusion mean?"}
  Server → Client:  {"token": "Pleural "}          (repeated)
  Server → Client:  {"event": "done"}               (end of response)
  Server → Client:  {"event": "error", "detail": …} (on failure)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_valid_job
from app.models.job import Job
from app.models.report import Report
from app.services.gemini_client import GeminiClient
from app.services.prompts import PromptTemplates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ── Medical disclaimer appended after every streamed response ────────
_DISCLAIMER = (
    "\n\n---\n_This analysis is for informational purposes only and "
    "does not constitute a medical diagnosis. Please consult a "
    "qualified healthcare professional for clinical decisions._"
)


# ── Keep the original POST endpoint for backwards compatibility ──────
class ChatRequest(BaseModel):
    """Incoming chat message tied to a job."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="User's question or prompt about the analysis.",
    )


class ChatResponse(BaseModel):
    """Chat response."""
    response: str
    job_id: uuid.UUID


@router.post(
    "/chat/{job_id}",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat about a job's analysis results (non-streaming)",
)
async def chat_about_job(
    body: ChatRequest,
    job: Job = Depends(get_valid_job),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Non-streaming chat endpoint.  For real-time streaming, use the
    WebSocket endpoint at ``/api/chat/ws/{job_id}``.
    """
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Chat is only available for completed jobs. "
                f"Current status: '{job.status}'."
            ),
        )

    # Fetch the report for context
    result = await db.execute(select(Report).where(Report.job_id == job.id))
    report = result.scalar_one_or_none()

    findings_context = "No report available."
    if report:
        findings_context = json.dumps(report.findings, indent=2)

    # Build prompt and call Gemini (non-streaming)
    try:
        client = GeminiClient()
        prompt = PromptTemplates.build_chat_prompt(
            findings_context=findings_context,
            user_question=body.message,
        )
        response_text = await client.generate_text(
            prompt=prompt,
            system_instruction=PromptTemplates.CHAT_SYSTEM_PROMPT,
            temperature=0.4,
        )
        response_text += _DISCLAIMER
    except Exception as exc:
        logger.error("Chat Gemini call failed: %s", exc)
        response_text = (
            "I apologise, but I was unable to process your question at "
            "this time. Please try again later." + _DISCLAIMER
        )

    return ChatResponse(response=response_text, job_id=job.id)


# ── WebSocket streaming endpoint ────────────────────────────────────
@router.websocket("/chat/ws/{job_id}")
async def chat_websocket(
    websocket: WebSocket,
    job_id: str,
):
    """
    Real-time streaming chat via WebSocket.

    Protocol
    --------
    1. Client connects to ``ws://.../api/chat/ws/{job_id}``.
    2. Server validates the job and sends ``{"event": "connected"}``.
    3. Client sends JSON: ``{"message": "your question"}``.
    4. Server streams back: ``{"token": "word "}`` frames.
    5. Server sends ``{"event": "done"}`` when the response is complete.
    6. Client can send another message (loop to step 3).
    7. Either side can close the connection.
    """
    await websocket.accept()
    logger.info("WebSocket chat connected for job %s", job_id)

    # ── Validate job ID format ────────────────────────────────────────
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        await websocket.send_json(
            {"event": "error", "detail": f"Invalid job ID format: {job_id}"}
        )
        await websocket.close(code=1008)
        return

    # ── Fetch job and report using a fresh DB session ─────────────────
    from app.db.session import async_session_factory

    async with async_session_factory() as db:
        result = await db.execute(select(Job).where(Job.id == job_uuid))
        job = result.scalar_one_or_none()

        if job is None:
            await websocket.send_json(
                {"event": "error", "detail": f"Job '{job_id}' not found."}
            )
            await websocket.close(code=1008)
            return

        if job.status != "completed":
            await websocket.send_json(
                {
                    "event": "error",
                    "detail": (
                        f"Chat is only available for completed jobs. "
                        f"Current status: '{job.status}'."
                    ),
                }
            )
            await websocket.close(code=1008)
            return

        # Fetch report for findings context
        rpt_result = await db.execute(
            select(Report).where(Report.job_id == job_uuid)
        )
        report = rpt_result.scalar_one_or_none()

    findings_context = "No analysis report available."
    if report and report.findings:
        findings_context = json.dumps(report.findings, indent=2)

    # ── Initialise Gemini client and conversation history ─────────────
    try:
        client = GeminiClient()
    except Exception as exc:
        await websocket.send_json(
            {"event": "error", "detail": f"AI service unavailable: {exc}"}
        )
        await websocket.close(code=1011)
        return

    conversation_history: list[dict[str, str]] = []

    # Notify client that connection is ready
    await websocket.send_json({"event": "connected", "job_id": job_id})

    # ── Message loop ──────────────────────────────────────────────────
    try:
        while True:
            # Wait for user message
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
                user_message = data.get("message", "").strip()
            except (json.JSONDecodeError, AttributeError):
                user_message = raw.strip()

            if not user_message:
                await websocket.send_json(
                    {"event": "error", "detail": "Empty message received."}
                )
                continue

            logger.info(
                "Chat message for job %s: %s",
                job_id,
                user_message[:100],
            )

            # Add to history
            conversation_history.append(
                {"role": "user", "content": user_message}
            )

            # Build context-aware prompt
            # Include last 10 conversation turns for continuity
            history_text = ""
            if len(conversation_history) > 1:
                recent = conversation_history[-10:]
                history_text = "\n".join(
                    f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                    for m in recent[:-1]  # exclude current message
                )
                history_text = (
                    f"\n══ CONVERSATION HISTORY ══\n"
                    f"{history_text}\n"
                    f"══ END HISTORY ══\n\n"
                )

            prompt = PromptTemplates.build_chat_prompt(
                findings_context=findings_context,
                user_question=f"{history_text}User question:\n{user_message}",
            )

            # Stream the response
            try:
                stream_response = await client.generate_text(
                    prompt=prompt,
                    system_instruction=PromptTemplates.CHAT_SYSTEM_PROMPT,
                    temperature=0.4,
                    stream=True,
                )

                full_response = ""

                # The stream_response is a callable that returns an iterator
                # We need to iterate it in a thread since it's synchronous
                def _consume_stream():
                    """Consume the stream synchronously."""
                    chunks = []
                    for chunk in stream_response:
                        if chunk.text:
                            chunks.append(chunk.text)
                    return chunks

                chunks = await asyncio.to_thread(_consume_stream)

                for chunk_text in chunks:
                    full_response += chunk_text
                    await websocket.send_json({"token": chunk_text})

                # Append disclaimer
                await websocket.send_json({"token": _DISCLAIMER})
                full_response += _DISCLAIMER

                # Signal completion
                await websocket.send_json({"event": "done"})

                # Store assistant response in history
                conversation_history.append(
                    {"role": "assistant", "content": full_response}
                )

            except WebSocketDisconnect:
                raise  # Re-raise to exit the loop
            except Exception as exc:
                logger.error("Streaming failed for job %s: %s", job_id, exc)
                error_msg = (
                    "I apologise, but I encountered an error processing "
                    "your question. Please try again."
                )
                await websocket.send_json({"token": error_msg})
                await websocket.send_json({"event": "done"})
                conversation_history.append(
                    {"role": "assistant", "content": error_msg}
                )

    except WebSocketDisconnect:
        logger.info(
            "WebSocket chat disconnected for job %s (%d messages exchanged).",
            job_id,
            len(conversation_history),
        )
    except Exception as exc:
        logger.error("WebSocket error for job %s: %s", job_id, exc)
        try:
            await websocket.send_json(
                {"event": "error", "detail": "Internal server error."}
            )
            await websocket.close(code=1011)
        except Exception:
            pass
