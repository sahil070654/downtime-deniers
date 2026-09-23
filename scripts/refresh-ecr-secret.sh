#!/bin/bash
kubectl delete secret ecr-secret --ignore-not-found
kubectl create secret docker-registry ecr-secret \
  --docker-server=302263069787.dkr.ecr.ap-south-1.amazonaws.com \
  --docker-username=AWS \
  --docker-password=$(aws ecr get-login-password --region ap-south-1)
