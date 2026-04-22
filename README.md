# Billing Service - Hospital Management System

## 1. Overview
Billing Service is one of the microservices in the Hospital Management System. It is responsible for managing billing records and exposing versioned REST APIs for billing-related operations.

This service supports:
- Generate bill from completed appointment
- View bill by ID
- List bills with pagination
- Search/filter bills by patient ID, appointment ID, and status
- Handle cancellation billing scenarios
- Adjust bill amounts
- Role-based access control (RBAC)
- Correlation ID propagation
- Standard error responses
- Structured JSON logging

This service follows the **database-per-service** pattern required by the assignment.

---

## 2. Assignment Mapping
This repository addresses the following assignment requirements for **Billing Service**:

- Billing record management
- Search functionality by patient ID, appointment ID, and bill status
- Versioned APIs using `/v1`
- Standard error response structure: `code`, `message`, `correlationId`
- Pagination and filtering support
- Docker containerization support
- Health endpoint
- OpenAPI 3.0 documentation
- Unit/API test cases
- Structured logging
- RBAC enforcement

---

## 3. Tech Stack
- Python 3.11+
- FastAPI
- SQLAlchemy
- SQLite (for local development)
- Pytest
- Docker
- HTTPX

---

## 4. Project Structure

```text
billing-service/
│── billing_service.py
│── common_utils.py
│── requirements.txt
│── Dockerfile
│── openapi_billing_service.yaml
│── billing.db
│── README.md
│── .gitignore
│── tests/
│   └── test_billing_service.py
```

## 5. Service Responsibilities

This service owns only billing-related data and does not directly access any other microservice database.

**Responsibilities**
 - Store billing records
 - Generate bill for completed appointments
 - Handle bill updates during cancellation scenarios
 - Adjust bill values based on business rules
 - Allow search and pagination for bill listing
 - Enforce service-level authorization

---

## 6. API Base URL
Local:
    http://localhost:9005

Swagger UI:
    http://localhost:9005/docs

Health:
    http://localhost:9005/health

Readiness:
    http://localhost:9005/ready

---

## 7. API Endpoints
**Health Endpoints**

| Method | Endpoint | Description                    |
| ------ | -------- | ------------------------------ |
| GET    | /health  | Basic service health check     |

**Billing Endpoints**

| Method | Endpoint                                             | Description                             |
| ------ | ---------------------------------------------------- |---------------------------------------- | 
| GET    | /v1/bills                                            | List bills with filters                 |
| GET    | /v1/bills/{bill_id}                                  | Get bill by ID                          |
| POST   | /v1/bills/generate-from-appointment/{appointment_id} | Generate bill for completed appointment |
| POST   | /v1/bills/handle-cancellation/{appointment_id}       | Handle cancellation billing flow        |
| POST   | /v1/bills/{bill_id}/adjust                           | Adjust an existing bill                 |

---

## 8. Query Parameters for List API

Endpoint: GET /v1/bills

| Parameter      | Type    | Required | Description              |
| -------------- | ------- | -------- | ------------------------ |
| patient_id     | integer | No       | Filter by patient ID     |
| appointment_id | integer | No       | Filter by appointment ID |
| status         | string  | No       | Filter by bill status    |
| skip           | integer | No       | Pagination offset        |
| limit          | integer | No       | Pagination page size     |

Example:
GET /v1/bills?patient_id=101&status=OPEN&skip=0&limit=10

---

## 9. RBAC
**Authorization header format:**
Authorization: Bearer <role>_test

**Examples:**

Authorization: Bearer admin_test

Authorization: Bearer reception_test

Authorization: Bearer doctor_test

**Allowed Roles by Endpoint:**
| Endpoint                                                  | admin | reception | billing |
| --------------------------------------------------------- | ----- | --------- | ------- |
| GET /v1/bills                                             | Yes   | Yes       | Yes     |
| GET /v1/bills/{bill_id}                                   | Yes   | Yes       | Yes     |
| POST /v1/bills/generate-from-appointment/{appointment_id} | Yes   | No        | Yes     |
| POST /v1/bills/handle-cancellation/{appointment_id}       | Yes   | No        | Yes     |
| POST /v1/bills/{bill_id}/adjust                           | Yes   | No        | Yes     |


---

## 10. Request and Response Examples

 ### Generate Bill From Appointment

**Request**

POST /v1/bills/generate-from-appointment/5001
Authorization: Bearer admin_test
Content-Type: application/json
X-Correlation-ID: bill-generate-001

**Response**
```json
{
  "bill_id": 1,
  "patient_id": 101,
  "appointment_id": 5001,
  "base_amount": 120.0,
  "tax_amount": 6.0,
  "total_amount": 126.0,
  "status": "OPEN",
  "created_at": "2026-04-19T12:34:56.000000"
}

```
 ### Handle Cancellation

**Request**

POST /v1/bills/handle-cancellation/5001
Authorization: Bearer admin_test
Content-Type: application/json
X-Correlation-ID: bill-cancel-001

```json
{
  "penalty": 0.5
}

```
**Response**
```json
{
  "bill_id": 1,
  "patient_id": 101,
  "appointment_id": 5001,
  "base_amount": 50.0,
  "tax_amount": 2.5,
  "total_amount": 52.5,
  "status": "OPEN",
  "created_at": "2026-04-19T12:34:56.000000"
}
```
---

## 11. Standard Error Response
```json
{
  "code": "404",
  "message": "Bill not found",
  "correlationId": "xxx"
}
```
| Status Code | Meaning                                   |
| ----------- | ----------------------------------------- |
| 400         | Invalid request / business rule violation |
| 401         | Invalid token                             |
| 403         | Role not allowed                          |
| 404         | Bill not found / Appointment not found    |
| 409         | Bill already exists for the appointment   |
| 422         | Validation error                          |
| 500         | Internal error                            |

---

## 12. Validation Rules
Penalty: must be between 0 and 1

Adjustment amount: numeric value

Appointment must exist before bill generation

Bills can only be generated for appointments with status COMPLETED

Paid bills cannot be edited directly in adjustment/certain cancellation cases

---

## 13. Cancellation and Adjustment Behavior
Cancellation flow updates an existing bill or creates a new penalty bill depending on the request

If penalty is 0:

PAID bill becomes REFUND
Unpaid bill becomes VOID

If penalty is greater than 0:

Bill amount is recalculated
Status is set to OPEN

Adjustment flow:

Updates bill base amount
Recalculates tax and total
Rejects changes for paid bills

---

## 14. Logging and Structured Output

This service uses structured JSON logging.

 - Logs are generated in JSON format for better monitoring
 - Key bill events are logged
 - Correlation ID is included in request/response flow for traceability

Example:

```json
{
  "timestamp": "2026-04-19T10:00:00Z",
  "service": "billing_service",
  "level": "INFO",
  "message": "Generated bill bill_id=1 appointment_id=5001 patient_id=101 bill_creation_latency_ms=15.42"
}

```
---

## 15. Correlation ID Support
Client-provided X-Correlation-ID propagated

Auto-generated if missing

Returned in response headers

Used for request tracing across services

---

## 16. Local Setup Instructions

 ### Step 1: Clone the repository
    ```bash
    git clone https://github.com/NandhiyaN/hms-billing-service
    cd billing-service
    ```
 ### Step 2: Create virtual environment
    ```bash
    python -m venv venv
    ```
 ### Step 3: Activate environment

    Windows:
        venv\Scripts\activate
    Linux/Mac:
        source venv/bin/activate

 ### Step 4: Install dependencies
    ```bash
    pip install -r requirements.txt
    pip install uvicorn
    ```

 ### Step 5: Run the service
    ```bash
    python -m uvicorn billing_service:app --reload --port 9005
    ```
 ### Step 6: Open Swagger UI
    http://localhost:9005/docs

---

## 17. Running Tests
Run:
python -m pytest tests/test_billing_service.py -v

Covers health, bill listing, missing bill handling, and RBAC validation.

---

## 18. Bruno API Collection
Bruno collection can be added under bruno/ for manual API validation and demo execution.

---

## 19. OpenAPI Specification

File: openapi_billing_service.yaml

This file documents:
- API endpoints
- Request and response schemas
- Standard error responses
- RBAC/security requirements
- Pagination and filtering
- Bill generation, cancellation, and adjustment APIs

---

## 20. Docker Support
Build: docker build -t billing-service .

Run: docker run -p 9005:9005 billing-service

Verify: curl http://localhost:9005/health

---

## 21. Kubernetes Readiness
Supports /health, /ready, containerized startup, env-based DB config.
Future manifests under k8s/.

---

## 22. Important Design Decisions
Database-per-service

Soft delete for integrity

Service-level RBAC

Structured logging

Versioned APIs under /v1

---

## 23. Future Improvements
JWT-based RBAC

PostgreSQL

Prometheus metrics

Alembic migrations

CI/CD pipeline

Kubernetes manifests

Audit fields

---

## 24. Author / Contribution
Scope: Billing APIs, validation, RBAC, structured logging, tests, Docker setup, and OpenAPI documentation.

