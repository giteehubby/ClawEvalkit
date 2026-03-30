#!/bin/bash
# Test: Skill Installation via ClawHub
# Tests installing a skill/extension from the ClawHub registry.
#
# Pass: Skill installs successfully and files exist
# Fail: Installation fails or files missing
#
# Note: To test muse specifically, use:
#   clawhub install alexander-morris/muse
# Currently testing with lulu-monitor as muse isn't in CLI registry yet.

test_skill_installation() {
  claw_header "TEST 11: Skill Installation (ClawHub)"

  local start_s
  local end_s
  local duration
  start_s=$(date +%s)

  local install_result
  local skill_name="lulu-monitor"
  local skill_dir="/tmp/claw-bench-skills"

  # Clean up any previous test
  case "$CLAW_MODE" in
    local)
      rm -rf "$skill_dir" 2>/dev/null || true
      # This benchmark is non-interactive, and lulu-monitor is currently flagged as suspicious
      # by clawhub. Use --force/--no-input so the test measures installation behavior instead
      # of failing on an interactive safety prompt. Also retry briefly on transient
      # registry rate limits, which otherwise make the benchmark flaky.
      install_result=""
      for attempt in 1 2 3; do
        install_result=$(timeout 90 npx clawhub install "$skill_name" --dir "$skill_dir" --force --no-input 2>&1) && break
        if [[ "$install_result" == *"Rate limit exceeded"* ]] || [[ "$install_result" == *"Resolving $skill_name"* ]]; then
          sleep 2
        else
          break
        fi
      done
      [[ -z "$install_result" ]] && install_result="INSTALL_FAILED"
      ;;
    ssh)
      ssh -i "$CLAW_SSH_KEY" $CLAW_SSH_OPTS "$CLAW_HOST" \
        "rm -rf $skill_dir 2>/dev/null; result=''; for attempt in 1 2 3; do result=\$(timeout 90 npx clawhub install '$skill_name' --dir '$skill_dir' --force --no-input 2>&1) && break; if echo \"\$result\" | grep -qi 'Rate limit exceeded'; then sleep 2; elif echo \"\$result\" | grep -qi 'Resolving $skill_name'; then sleep 2; else break; fi; done; if [ -z \"\$result\" ]; then result='INSTALL_FAILED'; fi; printf '%s' \"\$result\"" \
        > /tmp/clawhub_install_result.txt 2>&1 || true
      install_result=$(cat /tmp/clawhub_install_result.txt)
      ;;
    api)
      install_result="CLAW_NOT_IMPLEMENTED"
      ;;
  esac

  end_s=$(date +%s)
  duration=$(( (end_s - start_s) * 1000 ))

  # Check for success indicators
  if [[ "$install_result" == *"INSTALL_FAILED"* ]] || [[ "$install_result" == *"CLAW_NOT_IMPLEMENTED"* ]]; then
    claw_fail "Skill installation failed: $install_result" "skill_installation" "$duration"
  elif [[ "$install_result" == *"Installed"* ]] || [[ "$install_result" == *"OK"* ]]; then
    # Verify the skill directory exists
    local verify_result
    case "$CLAW_MODE" in
      local)
        verify_result=$(ls -la "$skill_dir/$skill_name" 2>&1)
        ;;
      ssh)
        verify_result=$(ssh -i "$CLAW_SSH_KEY" $CLAW_SSH_OPTS "$CLAW_HOST" \
          "ls -la '$skill_dir/$skill_name'" 2>&1)
        ;;
    esac

    if [[ "$verify_result" == *"SKILL.md"* ]] || [[ "$verify_result" == *"skill.md"* ]] || \
       [[ "$verify_result" == *"package.json"* ]] || [[ "$verify_result" == *"index"* ]]; then
      claw_pass "Skill installed and verified: $skill_name" "skill_installation" "$duration"

      # Cleanup
      case "$CLAW_MODE" in
        local)
          rm -rf "$skill_dir" 2>/dev/null || true
          ;;
        ssh)
          ssh -i "$CLAW_SSH_KEY" $CLAW_SSH_OPTS "$CLAW_HOST" "rm -rf '$skill_dir'" 2>/dev/null || true
          ;;
      esac
    else
      claw_fail "Skill installed but files not found: $verify_result" "skill_installation" "$duration"
    fi
  elif [[ "$install_result" == *"not found"* ]] || [[ "$install_result" == *"Not found"* ]]; then
    claw_fail "Skill not found in registry: $skill_name" "skill_installation" "$duration"
  else
    claw_fail "Unexpected install result: $install_result" "skill_installation" "$duration"
  fi
}
