# ClawBench Official NanoBotAgent Image
# Built on clawbase-nanobot:v1
#
# Build: docker build -f docker/clawbench/Dockerfile -t clawbase-nanobot:v1 .
#
# Extra dependencies needed:
# - tomli: for parsing task.toml files
# - pytest-json-report: for generating test reports

FROM clawbase-nanobot:v1

RUN pip install --no-cache-dir \
    -i https://pypi.org/simple/ \
    --trusted-host pypi.org \
    tomli \
    pytest \
    pytest-json-report \
    textblob
