#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

mkdir -p "$WORKSPACE/.github/workflows"

cat > "$WORKSPACE/.github/workflows/ci.yml" << 'WORKFLOW'
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.11"
  DOCKER_IMAGE: fastapi-webapp

jobs:
  test:
    name: Test & Lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run linting
        run: |
          python -m flake8 src/ tests/ --max-line-length=120
          python -m black --check src/ tests/

      - name: Run tests
        run: |
          python -m pytest tests/ -v --tb=short --cov=src --cov-report=xml

      - name: Upload coverage report
        if: matrix.python-version == '3.11'
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml

  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build Docker image
        run: |
          docker build -t ${{ env.DOCKER_IMAGE }}:${{ github.sha }} .
          docker tag ${{ env.DOCKER_IMAGE }}:${{ github.sha }} ${{ env.DOCKER_IMAGE }}:latest

  deploy:
    name: Deploy to AWS
    runs-on: ubuntu-latest
    needs: [test, build]
    if: github.ref == 'refs/heads/main'
    environment: production

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image to ECR
        env:
          ECR_REGISTRY: ${{ secrets.ECR_REGISTRY }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/${{ env.DOCKER_IMAGE }}:$IMAGE_TAG .
          docker push $ECR_REGISTRY/${{ env.DOCKER_IMAGE }}:$IMAGE_TAG
          docker tag $ECR_REGISTRY/${{ env.DOCKER_IMAGE }}:$IMAGE_TAG $ECR_REGISTRY/${{ env.DOCKER_IMAGE }}:latest
          docker push $ECR_REGISTRY/${{ env.DOCKER_IMAGE }}:latest

      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster fastapi-cluster \
            --service fastapi-webapp-service \
            --force-new-deployment
WORKFLOW

echo "Created .github/workflows/ci.yml in $WORKSPACE"
