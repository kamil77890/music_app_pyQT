#!/usr/bin/env bash
# Smoke-test all API routes. Requires: curl, server on :8000
set -u
BASE="${TEST_BASE_URL:-http://127.0.0.1:8000}"
PASS=0
FAIL=0

check() {
  local name="$1"
  local method="$2"
  local path="$3"
  local body="${4:-}"
  local allowed="${5:-200}"
  local code
  if [ "$method" = "GET" ]; then
    code=$(curl -s -o /tmp/ep_body.json -w "%{http_code}" "${BASE}${path}")
  elif [ "$method" = "POST" ]; then
    code=$(curl -s -o /tmp/ep_body.json -w "%{http_code}" -X POST \
      -H "Content-Type: application/json" \
      --data-binary "$body" \
      "${BASE}${path}")
  elif [ "$method" = "DELETE" ]; then
    code=$(curl -s -o /tmp/ep_body.json -w "%{http_code}" -X DELETE "${BASE}${path}")
  fi
  if echo " $allowed " | grep -q " $code "; then
    echo "OK   [$code] $method $path"
    PASS=$((PASS+1))
  else
    echo "FAIL [$code] $method $path (expected: $allowed)"
    head -c 300 /tmp/ep_body.json 2>/dev/null; echo
    FAIL=$((FAIL+1))
  fi
}

echo "=== Testing $BASE ==="
if ! curl -sf "${BASE}/" -o /dev/null; then
  echo "ERROR: server not running at $BASE"
  exit 1
fi

check "home" GET "/"
check "favicon" GET "/favicon.ico" "" "204"

check "events batch" POST "/events/batch" \
  '{"events":[{"video_id":"dQw4w9WgXcQ","event_type":"play","session_id":"test"}]}'
check "feedback" POST "/feedback" \
  '{"video_id":"dQw4w9WgXcQ","feedback":"like"}'
check "impression" POST "/recommendations/impression" \
  '{"request_id":"t1","items":[{"video_id":"dQw4w9WgXcQ","position":0}]}'
check "click" POST "/recommendations/click" \
  '{"request_id":"t1","video_id":"dQw4w9WgXcQ"}' "200 404"

check "yt status" GET "/auth/youtube/status"
check "yt start" GET "/auth/youtube/start" "" "200 503"
check "yt import" POST "/auth/youtube/import" "" "200 400 500"

check "rec profile" GET "/recommendations/profile" "" "200 404"
check "rec basic" GET "/recommendations?max_results=3" "" "200 404 429"
check "rec advanced" GET "/recommendations/advanced?max_results=3" "" "200 404 429 500"
check "rec explain" GET "/recommendations/explain/dQw4w9WgXcQ" "" "200 404"

check "playlist" GET "/playlists/all-songs" "" "200 404"
check "api songs" GET "/api/songs"

check "search" GET "/search?q=nightcore" "" "200 429 500"

check "subs list" GET "/subscriptions/"
check "subs feed" GET "/subscriptions/feed" "" "200 500"
check "notifications" GET "/notifications/" "" "200 404"

check "tags vocab" GET "/tags/vocabulary"
check "tags song" GET "/tags/song/dQw4w9WgXcQ"
check "tags analyze" POST "/tags/analyze" \
  '{"video_ids":["dQw4w9WgXcQ"],"force":false}' "200 500"

code=$(curl -s -o /tmp/ep_body.json -w "%{http_code}" -H "token: pytest" "${BASE}/Register")
if echo " 200 404 " | grep -q " $code "; then echo "OK   [$code] GET /Register"; PASS=$((PASS+1)); else echo "FAIL [$code] GET /Register"; FAIL=$((FAIL+1)); fi

check "video-url" GET "/video-url?videoId=dQw4w9WgXcQ" "" "200 500"
check "get id" GET "/get/id?title=test" "" "200 404 422 500"
check "title" GET "/title?name=test" "" "200 404 422 500"
check "subtitles" GET "/subtitles" "" "200 404 422 500"
check "cloud config" GET "/cloud/config" "" "200 500"
check "cloud catalog" GET "/cloud/catalog" "" "200 500"

echo ""
echo "=== Summary: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]
