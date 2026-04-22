from fastapi import FastAPI, HTTPException, Depends, APIRouter
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
from common_utils import (
    CorrelationIdMiddleware,
    setup_exception_handlers,
    require_role,
    setup_json_logger,
)
import os
import time
import httpx

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./billing.db")
APPOINTMENT_SERVICE_URL = os.getenv("APPOINTMENT_SERVICE_URL", "http://appointment-service:9003/v1")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class Bill(Base):
    __tablename__ = "bills"
    bill_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, index=True)
    appointment_id = Column(Integer, index=True)
    base_amount = Column(Float)
    tax_amount = Column(Float)
    total_amount = Column(Float)
    status = Column(String) 
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Schemas
class BillResponse(BaseModel):
    bill_id: int
    patient_id: int
    appointment_id: int
    base_amount: float
    tax_amount: float
    total_amount: float
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class CancelRequest(BaseModel):
    penalty: float

    @field_validator("penalty")
    @classmethod
    def validate_penalty(cls, value):
        if value < 0 or value > 1:
            raise ValueError("penalty must be between 0 and 1")
        return value

class AdjustmentRequest(BaseModel):
    adjustment_amount: float
    reason: str

logger = setup_json_logger("billing_service")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(title="Billing Service")
app.add_middleware(CorrelationIdMiddleware)
setup_exception_handlers(app)

@app.get("/health")
def health_check(): return {"status": "ok", "service": "billing"}

router = APIRouter(prefix="/v1")

async def fetch_appointment(appointment_id: int):
    """
    Calls Appointment Service to validate the appointment before bill generation.
    Expected appointment payload must contain appointment_id, patient_id, and status.
    """
    url = f"{APPOINTMENT_SERVICE_URL}/appointments/{appointment_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers={"Authorization": "Bearer admin_test"})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

@router.get("/bills", response_model=list[BillResponse])
def get_bills(
    skip: int = 0,
    limit: int = 10,
    patient_id: int | None = None,
    appointment_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["billing", "admin", "reception"]))
):
    query = db.query(Bill)

    if patient_id is not None:
        query = query.filter(Bill.patient_id == patient_id)
    if appointment_id is not None:
        query = query.filter(Bill.appointment_id == appointment_id)
    if status is not None:
        query = query.filter(Bill.status == status)

    return query.offset(skip).limit(limit).all()

@router.get("/bills/{bill_id}", response_model=BillResponse)
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["billing", "admin", "reception"]))
):
    bill = db.query(Bill).filter(Bill.bill_id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill

@router.post("/bills/generate-from-appointment/{appointment_id}", response_model=BillResponse)
async def generate_bill(
    appointment_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["billing", "admin"]))
):
    start_time = time.perf_counter()

    existing_bill = db.query(Bill).filter(Bill.appointment_id == appointment_id).first()
    if existing_bill:
        raise HTTPException(status_code=409, detail="Bill already exists for this appointment")

    appointment = await fetch_appointment(appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appointment_status = appointment.get("status")
    if appointment_status != "COMPLETED":
        raise HTTPException(status_code=400, detail="Bills can only be generated for COMPLETED appointments")

    patient_id = appointment["patient_id"]

    consultation_amount = 100.0
    medication_amount = 20.0
    base_amount = consultation_amount + medication_amount
    tax_amount = round(base_amount * 0.05, 2)
    total_amount = round(base_amount + tax_amount, 2)

    db_bill = Bill(
        patient_id=patient_id,
        appointment_id=appointment_id,
        base_amount=base_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        status="OPEN"
    )
    db.add(db_bill)
    db.commit()
    db.refresh(db_bill)

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    logger.info(
        f"Generated bill bill_id={db_bill.bill_id} appointment_id={appointment_id} "
        f"patient_id={patient_id} bill_creation_latency_ms={latency_ms}"
    )

    return db_bill

@router.post("/bills/handle-cancellation/{appointment_id}", response_model=BillResponse)
def handle_cancellation(
    appointment_id: int,
    req: CancelRequest,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["billing", "admin"]))
):
    bill = db.query(Bill).filter(Bill.appointment_id == appointment_id).first()

    if req.penalty == 0.0:
        if not bill:
            raise HTTPException(status_code=400, detail="No pre-existing bill found to void.")

        if bill.status == "PAID":
            bill.status = "REFUND"
        else:
            bill.status = "VOID"

        db.commit()
        db.refresh(bill)

        logger.info(
            f"Handled cancellation appointment_id={appointment_id} penalty={req.penalty} bill_status={bill.status}"
        )
        return bill

    base = round(100.0 * req.penalty, 2)
    tax = round(base * 0.05, 2)
    total = round(base + tax, 2)

    if bill:
        if bill.status == "PAID":
            raise HTTPException(status_code=400, detail="Paid bills cannot be edited directly. Use adjustments.")

        bill.base_amount = base
        bill.tax_amount = tax
        bill.total_amount = total
        bill.status = "OPEN"
        db.commit()
        db.refresh(bill)
    else:
        bill = Bill(
            patient_id=1,
            appointment_id=appointment_id,
            base_amount=base,
            tax_amount=tax,
            total_amount=total,
            status="OPEN"
        )
        db.add(bill)
        db.commit()
        db.refresh(bill)

    logger.info(
        f"Handled cancellation appointment_id={appointment_id} penalty={req.penalty} bill_id={bill.bill_id}"
    )
    return bill

@router.post("/bills/{bill_id}/adjust", response_model=BillResponse)
def adjust_bill(
    bill_id: int,
    req: AdjustmentRequest,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["billing", "admin"]))
):
    bill = db.query(Bill).filter(Bill.bill_id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    if bill.status == "PAID":
        raise HTTPException(status_code=400, detail="Paid bills cannot be edited directly. Use refund flow.")

    bill.base_amount = round(bill.base_amount + req.adjustment_amount, 2)
    bill.tax_amount = round(bill.base_amount * 0.05, 2)
    bill.total_amount = round(bill.base_amount + bill.tax_amount, 2)

    db.commit()
    db.refresh(bill)

    logger.info(
        f"Adjusted bill bill_id={bill.bill_id} adjustment_amount={req.adjustment_amount} reason={req.reason}"
    )
    return bill

app.include_router(router)
