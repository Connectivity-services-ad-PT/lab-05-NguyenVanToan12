import os
import uuid
import time
import json
import requests
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

SERVICE_NAME = os.getenv("SERVICE_NAME", "analytics-alert")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "local-dev-jwt-token-67890")

# Database Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "lab05")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "lab05pass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "iotdb")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai-service:9000")

app = FastAPI(
    title="FIT4110 Lab 05 - Analytics & Alert Service",
    version=SERVICE_VERSION,
    description="Dockerized Analytics & Alert API with TimescaleDB integration and AI service coordination.",
)


class SeverityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HealthResponse(BaseModel):
    status: str = Field(default="UP", examples=["UP"])


class CreateAlertRequest(BaseModel):
    sourceService: str = Field(..., examples=["core-business"])
    alertType: str = Field(..., examples=["UNAUTHORIZED_ACCESS"])
    severity: SeverityEnum = Field(..., examples=["HIGH"])
    message: str = Field(..., examples=["Phat hien doi tuong la dot nhap vao phong lap chat luong cao"])
    relatedEventId: Optional[str] = Field(default=None, examples=["evt_0196fb3d-7ad7-7d1e-9f49-5d5148d2bcba"])


class Alert(BaseModel):
    id: str = Field(..., examples=["ALT-0196fb3d-bcd7-7d1e-9f49-5d5148d2b666"])
    alertType: str = Field(..., examples=["UNAUTHORIZED_ACCESS"])
    severity: SeverityEnum = Field(..., examples=["HIGH"])
    message: str = Field(..., examples=["Phat hien doi tuong la dot nhap vao phong lap chat luong cao"])
    relatedEventId: Optional[str] = Field(default=None, examples=["evt_0196fb3d-7ad7-7d1e-9f49-5d5148d2bcba"])


class Problem(BaseModel):
    type: str = Field(default="about:blank", examples=["https://api.smartcampus.edu.vn/errors/unauthorized"])
    title: str = Field(..., examples=["Unauthorized Access"])
    status: int = Field(..., ge=400, le=599, examples=[401])
    detail: str = Field(..., examples=["Token cung cap khong hop le hoac da het han."])


def get_db_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname=POSTGRES_DB,
        cursor_factory=RealDictCursor
    )


@app.on_event("startup")
def startup_event():
    retries = 10
    conn = None
    for i in range(retries):
        try:
            conn = get_db_connection()
            break
        except Exception as e:
            print(f"Waiting for database connection... ({i+1}/{retries}). Error: {e}")
            time.sleep(2)
    
    if not conn:
        print("Could not establish connection to the database. Startup tasks aborted.")
        return

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id VARCHAR(50) PRIMARY KEY,
                    alert_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    related_event_id VARCHAR(50),
                    details JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

            cur.execute("SELECT id FROM alerts WHERE id IN ('ALT-001', 'ALT-002')")
            existing_ids = {row['id'] for row in cur.fetchall()}

            if 'ALT-001' not in existing_ids:
                cur.execute("""
                    INSERT INTO alerts (id, alert_type, severity, message, details)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    'ALT-001',
                    'FIRE',
                    'HIGH',
                    'Fire detected in LAB-401',
                    json.dumps({'location': 'LAB-401', 'temperature': 85.5})
                ))
            if 'ALT-002' not in existing_ids:
                cur.execute("""
                    INSERT INTO alerts (id, alert_type, severity, message, details)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    'ALT-002',
                    'SECURITY',
                    'HIGH',
                    'Intruder detected by CAM-GATE-01',
                    json.dumps({'cameraId': 'CAM-GATE-01', 'suspectDetected': True})
                ))
            conn.commit()
            print("Database tables initialized and pre-seeded successfully.")
    except Exception as e:
        print(f"Error during database initialization: {e}")
    finally:
        if conn:
            conn.close()


def build_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    problem_type: Optional[str] = None,
) -> Dict:
    if not problem_type:
        if status_code == 401:
            problem_type = "https://api.smartcampus.edu.vn/errors/unauthorized"
        elif status_code == 403:
            problem_type = "https://api.smartcampus.edu.vn/errors/forbidden"
        elif status_code == 404:
            problem_type = "https://api.smartcampus.edu.vn/errors/not-found"
        elif status_code == 422:
            problem_type = "https://api.smartcampus.edu.vn/errors/validation-error"
        else:
            problem_type = f"https://api.smartcampus.edu.vn/errors/{status_code}"

    return {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        problem = exc.detail
    else:
        title = "HTTP Error"
        if exc.status_code == 401:
            title = "Unauthorized"
        elif exc.status_code == 403:
            title = "Forbidden"
        elif exc.status_code == 404:
            title = "Not Found"
            
        problem = build_problem(
            status_code=exc.status_code,
            title=title,
            detail=str(exc.detail),
        )

    return JSONResponse(
        status_code=exc.status_code,
        content=problem,
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first_error.get("loc", []) if item != "body")
    message = first_error.get("msg", "Request validation error")
    detail = f"{location}: {message}" if location else message

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation error",
            detail=detail,
        ),
        media_type="application/problem+json",
    )


def verify_bearer_token(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    allowed_tokens = {AUTH_TOKEN, "local-dev-jwt-token-67890", "local-dev-token", "mock-jwt-token-12345"}

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = authorization.split(" ", 1)[1]
    if token not in allowed_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )


@app.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
def health(request: Request) -> Optional[HealthResponse]:
    if request.method == "HEAD":
        return None

    # Check Database Connection
    db_ok = False
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception as e:
        print(f"Healthcheck Failure - Database is unreachable: {e}")

    # Check AI Service Status
    ai_ok = False
    try:
        r = requests.get(f"{AI_SERVICE_URL}/health", timeout=3)
        if r.status_code == 200:
            ai_ok = True
        else:
            print(f"Healthcheck Warning - AI Service returned status code: {r.status_code}")
    except Exception as e:
        print(f"Healthcheck Failure - AI Service is unreachable: {e}")

    if not db_ok or not ai_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "DOWN",
                "database": "UP" if db_ok else "DOWN",
                "ai_service": "UP" if ai_ok else "DOWN"
            }
        )

    return HealthResponse(status="UP")


@app.post(
    "/alerts",
    response_model=Alert,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_bearer_token)],
    responses={
        401: {"model": Problem},
        422: {"model": Problem},
    },
)
def create_alert(payload: CreateAlertRequest) -> Dict:
    alert_id = f"ALT-{uuid.uuid4().hex[:8]}"
    
    details = {
        "sourceService": payload.sourceService
    }

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO alerts (id, alert_type, severity, message, related_event_id, details)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                alert_id,
                payload.alertType,
                payload.severity.value,
                payload.message,
                payload.relatedEventId,
                json.dumps(details)
            ))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error persisting new alert into TimescaleDB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database insertion failed: {e}"
        )

    return {
        "id": alert_id,
        "alertType": payload.alertType,
        "severity": payload.severity,
        "message": payload.message,
        "relatedEventId": payload.relatedEventId,
    }


@app.get(
    "/alerts/recent",
    response_model=List[Alert],
    dependencies=[Depends(verify_bearer_token)],
    responses={
        401: {"model": Problem},
        403: {"model": Problem},
    },
)
def get_recent_alerts(
    response: Response,
    limit: int = Query(default=10, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
) -> List[Dict]:
    response.headers["X-Next-Cursor"] = "next-page-cursor-value"
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, alert_type, severity, message, related_event_id
                FROM alerts
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"Error retrieving recent alerts from TimescaleDB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database fetch failed: {e}"
        )

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "alertType": row["alert_type"],
            "severity": row["severity"],
            "message": row["message"],
            "relatedEventId": row["related_event_id"]
        })

    # Return standard JSON array
    return results


@app.get(
    "/alerts/{alertId}",
    dependencies=[Depends(verify_bearer_token)],
    responses={
        200: {
            "description": "Alert details",
            "content": {
                "application/json": {
                    "examples": {
                        "fire_alert": {
                            "value": {
                                "alertType": "FIRE",
                                "id": "ALT-001",
                                "location": "LAB-401",
                                "temperature": 85.5,
                            }
                        },
                        "security_alert": {
                            "value": {
                                "alertType": "SECURITY",
                                "id": "ALT-002",
                                "cameraId": "CAM-GATE-01",
                                "suspectDetected": True,
                              }
                          },
                      }
                  }
              },
          },
          401: {"model": Problem},
          404: {"model": Problem},
      },
  )
def get_alert_by_id(alertId: str) -> Dict:
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, alert_type, severity, message, related_event_id, details
                FROM alerts
                WHERE id = %s
            """, (alertId,))
            row = cur.fetchone()
        conn.close()
    except Exception as e:
        print(f"Error querying alert {alertId} from TimescaleDB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {e}"
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alertId} not found",
        )

    details = row["details"] or {}
    result = {
        "id": row["id"],
        "alertType": row["alert_type"],
        "severity": row["severity"],
        "message": row["message"],
        "relatedEventId": row["related_event_id"]
    }
    
    # Merge custom details into output representation (Polymorphism support)
    for k, v in details.items():
        result[k] = v

    return result