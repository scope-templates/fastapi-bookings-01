from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.http import internal_error_response
from app.routers import bookings, browse, events, reports, session

app = FastAPI(title="Studio Slot", version="0.6.1")
app.include_router(session.router)
app.include_router(events.router)
app.include_router(browse.router)
app.include_router(bookings.router)
app.include_router(reports.router)


@app.exception_handler(Exception)
async def unplanned_failure(request: Request, err: Exception) -> JSONResponse:
    return internal_error_response(err)
