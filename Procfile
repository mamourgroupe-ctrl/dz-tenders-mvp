web: python -m webapp.cli init-db && python -m uvicorn webapp.web.main:create_app --factory --host 0.0.0.0 --port $PORT
api: python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT
