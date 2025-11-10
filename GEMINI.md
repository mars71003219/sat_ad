## Project Overview

This project is a satellite telemetry anomaly detection system that uses an event-driven batch processing architecture. It collects telemetry data from multiple satellites in batches, and when a batch transmission is complete, it automatically triggers inference to detect anomalies.

**Main Technologies:**

*   **Backend:** Python, FastAPI, Celery, SQLAlchemy
*   **Frontend:** React.js
*   **Message Queue:** Kafka, RabbitMQ
*   **Database:** PostgreSQL, VictoriaMetrics
*   **Inference:** Triton Inference Server
*   **Containerization:** Docker, Docker Compose

**Architecture:**

The system is composed of several microservices that communicate via Kafka and RabbitMQ.

1.  **Batch Simulator:** Simulates satellite data transmission.
2.  **Kafka:** Acts as a message bus for telemetry data and inference results.
3.  **Victoria Consumer:** Consumes data from Kafka and stores it in VictoriaMetrics.
4.  **Batch Inference Trigger:** Detects the completion of a batch and triggers the inference process.
5.  **Celery:** Manages the distributed task queue for inference.
6.  **Analysis Worker:** Performs the actual inference tasks.
7.  **Triton Server:** Serves the machine learning models for inference.
8.  **PostgreSQL:** Stores system configuration.
9.  **Operation Server:** Provides a REST API for the frontend.
10. **Frontend:** A React-based dashboard for monitoring and visualization.
11. **Nginx:** Acts as a reverse proxy for the frontend and backend services.

## Building and Running

**Prerequisites:**

*   Docker and Docker Compose

**Running the project:**

1.  **Initialize Kafka:**
    ```bash
    bash init_kafka.sh
    ```

2.  **Start all services:**
    ```bash
    docker-compose up -d
    ```

3.  **Run the simulator:**
    ```bash
    docker-compose run --rm batch-simulator
    ```

**Accessing the services:**

*   **Dashboard:** `http://localhost`
*   **Operation Server API:** `http://localhost/api`
*   **Kafka UI:** `http://localhost:8080`
*   **RabbitMQ Management:** `http://localhost:15672` (guest/guest)
*   **Flower (Celery):** `http://localhost:5555`
*   **VictoriaMetrics:** `http://localhost:8428`

## Development Conventions

*   The project is structured as a set of microservices, each with its own `requirements.txt` or `package.json` file.
*   The backend services are written in Python, and the frontend is a React application.
*   The services are containerized using Docker and orchestrated with Docker Compose.
*   The backend follows a standard FastAPI project structure, with API routes, database clients, and other components organized into separate modules.
*   The frontend uses a component-based architecture, with components for displaying charts, stats, and other UI elements.
*   The project uses environment variables for configuration, which are defined in the `docker-compose.yml` file.
