# Task: CI/CD Pipeline Design

You are given a project description for a Python web application. Design a complete CI/CD pipeline using GitHub Actions.

## Input Files

- `workspace/project_info.json` — JSON describing the project: framework, test framework, deployment target, branch strategy, and requirements

## Goal

Create a production-ready GitHub Actions workflow file.

## Requirements

1. Read `workspace/project_info.json` for project details.
2. Create `workspace/.github/workflows/ci.yml` — a GitHub Actions workflow.

### Workflow Must Include

#### Triggers
- `on.push` — trigger on push to `main` and `develop` branches
- `on.pull_request` — trigger on PRs to `main`

#### Jobs & Steps
The workflow should have at minimum a `test` job and a `deploy` job:

**Test Job:**
- Checkout code (`actions/checkout`)
- Set up Python (`actions/setup-python`)
- Install dependencies (`pip install -r requirements.txt`)
- Run linting (flake8 or ruff)
- Run tests with pytest
- Optionally: upload test results / coverage

**Build Job (or step):**
- Build Docker image
- Optionally push to registry

**Deploy Job:**
- Only runs on the `main` branch
- Depends on the test job passing
- Contains deployment steps (AWS ECS, EC2, or similar)
- Uses GitHub secrets for credentials

#### Additional Requirements
- Use proper action versions (e.g., `actions/checkout@v4`)
- Define environment variables where appropriate
- The YAML must be syntactically valid
- Include meaningful job/step names

## Notes

- The workflow should be production-quality.
- Matrix testing across multiple Python versions is a bonus.
- Caching pip dependencies is a bonus.
- Branch protection (deploy only on main) is mandatory.
