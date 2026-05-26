# Ubuntu Docker Operation

This runs APR Gateway as an Ubuntu-based container.

## Build

```bash
cd /path/to/apr_gateway
docker compose -f docker-compose.ubuntu.yml build
```

## Run

```bash
docker compose -f docker-compose.ubuntu.yml up -d
```

## Check

```bash
curl http://127.0.0.1:8080/health
docker logs -f apr-gateway
```

Expected MQTT flow:

```text
218.146.225.166:1883 iot/sensor/#
  -> APR Gateway
  -> 218.146.225.166:1883 iot/optimized/#
```

## Stop

```bash
docker compose -f docker-compose.ubuntu.yml down
```

## Notes

- The image installs both `requirements.txt` and `requirements-ml.txt`.
- Windows-only `.python_packages/` is excluded from the Docker build context.
- Runtime config is loaded from `.env`.
- The model loader prefers `models/xgb_preprocessor.joblib` + `models/xgb_model.json`, then falls back to `models/xgb_model.joblib`.
