#!/bin/bash
# Refresh the ECR pull secret in the default namespace.
# Run after every EC2 restart — ECR tokens expire in ~12 hours.

set -euo pipefail

NAMESPACE=default
AWS_REGION=ap-south-1
ECR_REGISTRY=302263069787.dkr.ecr.ap-south-1.amazonaws.com

echo "[refresh-ecr-secret] Fetching new ECR token..."
TOKEN=$(aws ecr get-login-password --region "$AWS_REGION")

if [ -z "$TOKEN" ]; then
  echo "[refresh-ecr-secret] ERROR: empty token. Check IAM role / AWS CLI."
  exit 1
fi

echo "[refresh-ecr-secret] Deleting old secret (if present)..."
kubectl delete secret ecr-secret -n "$NAMESPACE" --ignore-not-found

echo "[refresh-ecr-secret] Creating new secret..."
kubectl create secret docker-registry ecr-secret \
  --docker-server="$ECR_REGISTRY" \
  --docker-username=AWS \
  --docker-password="$TOKEN" \
  -n "$NAMESPACE"

echo "[refresh-ecr-secret] Done. Current secret:"
kubectl get secret ecr-secret -n "$NAMESPACE"
