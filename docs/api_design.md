# Hajeen AI - Cognitive Operating System API Design

This document outlines the proposed API design for the Hajeen Cognitive Operating System. The APIs are designed to facilitate communication between the new cognitive components and the existing Brain V3 architecture, as well as to provide external interfaces for interacting with the system.

## 1. Core Principles

*   **RESTful Architecture:** The APIs will follow RESTful principles, utilizing standard HTTP methods (GET, POST, PUT, DELETE) and status codes.
*   **JSON Payloads:** Data will be exchanged in JSON format for both requests and responses.
*   **Versioning:** APIs will be versioned (e.g., `/api/v1/`) to ensure backward compatibility as the system evolves.
*   **Authentication & Authorization:** Secure access will be enforced using API keys or OAuth 2.0 tokens.
*   **Asynchronous Processing:** Long-running tasks (e.g., complex reasoning, experiments) will utilize asynchronous endpoints, returning task IDs for status polling.

## 2. Internal APIs (Component-to-Component)

These APIs facilitate communication between the internal modules of the Cognitive Operating System.

### 2.1. Cognitive Compiler API

**Endpoint:** `/internal/compiler`

*   **POST `/compile`**
    *   **Description:** Submits raw input for cognitive compilation.
    *   **Request Body:** `{"raw_input": "string", "context": "object"}`
    *   **Response:** `{"event_id": "uuid", "status": "processing"}`

### 2.2. Concept Engine API

**Endpoint:** `/internal/concepts`

*   **POST `/`**
    *   **Description:** Creates a new concept.
    *   **Request Body:** `{"name": "string", "definition": "string"}`
    *   **Response:** `{"concept_id": "uuid"}`
*   **GET `/{concept_id}`**
    *   **Description:** Retrieves a concept by ID.
    *   **Response:** Concept object (JSON).
*   **PUT `/{concept_id}`**
    *   **Description:** Updates an existing concept.
    *   **Request Body:** Concept update object (JSON).
    *   **Response:** `{"status": "success"}`

### 2.3. Evidence Court API

**Endpoint:** `/internal/evidence`

*   **POST `/evaluate`**
    *   **Description:** Submits information for evaluation.
    *   **Request Body:** `{"information": "object", "source": "object"}`
    *   **Response:** `{"confidence_score": "float", "report": "object"}`

### 2.4. Hypothesis Engine API

**Endpoint:** `/internal/hypotheses`

*   **POST `/generate`**
    *   **Description:** Requests generation of hypotheses for a given problem.
    *   **Request Body:** `{"problem_statement": "string", "context": "object"}`
    *   **Response:** `{"hypotheses": ["object"]}`

### 2.5. Model Society API

**Endpoint:** `/internal/models`

*   **POST `/route`**
    *   **Description:** Routes a query to the appropriate model(s).
    *   **Request Body:** `{"query": "string", "domain": "string"}`
    *   **Response:** `{"model_responses": ["object"], "consensus": "boolean"}`

### 2.6. Experience Memory API

**Endpoint:** `/internal/experience`

*   **POST `/store`**
    *   **Description:** Stores a new cognitive experience.
    *   **Request Body:** Experience object (JSON).
    *   **Response:** `{"experience_id": "uuid"}`
*   **GET `/search`**
    *   **Description:** Searches for past experiences based on criteria.
    *   **Query Parameters:** `?task=string&result=string`
    *   **Response:** `{"experiences": ["object"]}`

## 3. External APIs (Client-to-System)

These APIs are exposed to external clients (e.g., user interfaces, other applications) to interact with the Hajeen Cognitive Operating System.

### 3.1. Interaction API

**Endpoint:** `/api/v1/interact`

*   **POST `/`**
    *   **Description:** The primary endpoint for user interaction. Submits a query or task to the system.
    *   **Request Body:** `{"query": "string", "session_id": "string"}`
    *   **Response:** `{"response": "string", "confidence": "float", "reasoning_trace_id": "uuid"}`

### 3.2. Knowledge API

**Endpoint:** `/api/v1/knowledge`

*   **GET `/concept/{name}`**
    *   **Description:** Retrieves information about a specific concept from the Concept Engine.
    *   **Response:** Concept details, including definition, properties, and relationships.
*   **GET `/causal-links`**
    *   **Description:** Queries the Knowledge Physics Engine for causal relationships.
    *   **Query Parameters:** `?cause=string&effect=string`
    *   **Response:** List of causal relationships with confidence scores.

### 3.3. System Status API

**Endpoint:** `/api/v1/system`

*   **GET `/health`**
    *   **Description:** Returns the overall health and status of the Cognitive Operating System components.
    *   **Response:** `{"status": "healthy", "components": {"compiler": "ok", "memory": "ok", ...}}`
*   **GET `/evolution/version`**
    *   **Description:** Retrieves the current cognitive version of the system.
    *   **Response:** `{"version": "string", "last_updated": "datetime"}`

## 4. Integration with Brain V3 APIs

The new APIs will be designed to wrap or integrate with existing Brain V3 APIs where appropriate. For example, the `/api/v1/interact` endpoint will internally call the `CognitiveCompiler`, which in turn may utilize Brain V3's `ReasoningEngine` and `MemoryFabric` via their respective internal interfaces.

## 5. Error Handling

All APIs will return standard HTTP error codes along with a JSON body containing a detailed error message.

*   **400 Bad Request:** Invalid input data.
*   **401 Unauthorized:** Missing or invalid authentication credentials.
*   **403 Forbidden:** Insufficient permissions to access the resource.
*   **404 Not Found:** The requested resource does not exist.
*   **500 Internal Server Error:** An unexpected error occurred within the system.

**Error Response Format:**
```json
{
  "error": {
    "code": 400,
    "message": "Invalid request format. Missing required field 'query'."
  }
}
```
