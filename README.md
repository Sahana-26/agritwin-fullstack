# AgriTwin Platform (AI + Full Stack Agriculture Intelligence System)

AgriTwin is a full-stack web platform that combines machine learning, data analytics, and intelligent farm management tools to support crop monitoring and yield prediction.

The system is built using a modular backend architecture with REST APIs, ML inference services, and an interactive dashboard for visualization and decision-making.

The same backend APIs are also consumed by a **mobile application**, making the system cross-platform.

---

## Key Features

### AI & Machine Learning

* Crop disease prediction from leaf images
* Yield prediction based on soil and environmental parameters
* Recommendation system for crop health and severity analysis
* Prediction history tracking for farmers and plots

### Data & Analytics

* Crop performance tracking over time
* Yield history and trend analysis
* Farm-level summary and insights
* Interactive charts (trend, bar, pie, histogram)

### Full Stack System

* REST API-based backend using Django REST Framework
* Web dashboard for farm management and monitoring
* Mobile application support using same APIs
* Real-time data visualization
* Secure authentication and role-based access

### Farm Management System

* Farmer profile management
* Farm plot creation and tracking
* Crop profiling per plot
* Data collection points for monitoring farm conditions

---

## Machine Learning Modules

### Crop Disease Prediction

* Input: Crop type + leaf image
* Output:

  * Disease classification
  * Confidence score
  * Severity level
  * Recommendation for treatment
  * Yield impact estimation

### Yield Prediction

* Input:

  * Soil parameters
  * Weather conditions
  * Fertilizer and irrigation data
* Output:

  * Predicted yield (kg/ha)
* Stores prediction history for analytics

---

## System Architecture

* Backend: Django + Django REST Framework
* Database: PostgreSQL
* ML Inference Layer: Integrated model services inside backend APIs
* Frontend: Interactive web dashboard (JavaScript-based UI)
* Mobile: APIs consumed by mobile application
* Visualization: Plotly charts and dynamic UI components
* Authentication: Secure login system with user-based access

---

## API Endpoints

### Farm & User Management

* `/api/farmers/me/`
* `/api/plots/`
* `/api/crops/`
* `/api/summary/`

### Machine Learning APIs

* `POST /api/predict/` → Crop disease prediction
* `POST /api/yield/predict/` → Yield prediction

### Analytics APIs

* `/api/yield/history/`
* `/api/trends/`
* `/api/dashboard/config/`

### Visualization APIs

* `/api/analysis/<run_id>/charts/`
* `/api/analysis/<run_id>/inspect/`

---

## Setup Instructions

### 1. Start Database

```
docker compose up -d
```

### 2. Install Dependencies

```
pip install -r requirements.txt
```

### 3. Run Migrations

```
python manage.py migrate
```

### 4. Load Data

```
python manage.py backfill_historical
python manage.py refresh_future
```

### 5. Run Server

```
python manage.py runserver
```