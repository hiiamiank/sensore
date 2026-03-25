# Sensore

A web-based pressure ulcer prevention application built for Graphene Trace.

## Tech Stack
- Python 3.13 / Django 6
- MySQL
- HTML, CSS, JavaScript
- Chart.js

## Setup Instructions

1. Clone the repository
```
   git clone https://github.com/hiiamiank/sensore.git
   cd sensore
```

2. Create and activate virtual environment
```
   python -m venv venv
   venv\Scripts\activate  # Windows
```

3. Install dependencies
```
   pip install -r requirements.txt
```

4. Create MySQL database
```sql
   CREATE DATABASE sensore_db CHARACTER SET utf8mb4;
```

5. Configure database credentials in `core/settings.py`

6. Run migrations
```
   python manage.py migrate
```

7. Create superuser
```
   python manage.py createsuperuser
```

8. Run the development server
```
   python manage.py runserver
```

## Running Tests
```
python manage.py test sensore --verbosity=2
```