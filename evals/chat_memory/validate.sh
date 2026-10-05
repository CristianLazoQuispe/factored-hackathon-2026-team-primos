#!/usr/bin/env bash
# Validates the chat memory end to end through the API, with no browser. It talks to the real agent, so it
# needs the API running with CHAT_MEMORY_ENABLED=true (make dev, or make up) and a model available.
#
#   bash evals/chat_memory/validate.sh        (from the root of the repository)
#
# What it does: two demo customers write to the chat, the first one's conversations are listed, opened and
# hidden, and the database is asked whether the hidden ones are still there. It only runs against a LOCAL
# API: it writes conversations, and it must never be pointed at production by mistake.
#
# It starts by hiding what the two demo customers already had from earlier runs. Nothing is deleted (the rows
# stay, only out of sight), and it is what makes every run start with nothing to remember, so that "what did I
# ask before?" has one answer and not a pile of old test questions.
#
# Optional: API=http://localhost:8080  A=demo-mx-duplicate@demo.bank  B=demo-ar-fraud@demo.bank  DB=postgresql://agent:agent@localhost:5432/agent
# (the demo e-mails always sign in; their password is the same e-mail)
set -u
API=${API:-http://localhost:8080}
A=${A:-demo-mx-duplicate@demo.bank}
B=${B:-demo-ar-fraud@demo.bank}
DB=${DB:-postgresql://agent:agent@localhost:5432/agent}

case "$API" in
  http://localhost:*|http://127.0.0.1:*) ;;
  *) echo "Refusing to run against $API: this writes conversations and only runs against a local API." >&2; exit 2 ;;
esac
command -v python3 >/dev/null || { echo "python3 is needed to read the answers" >&2; exit 2; }

pass=0; fail=0
ok()    { echo "  ✓ $1"; pass=$((pass + 1)); }
bad()   { echo "  ✗ $1"; fail=$((fail + 1)); }
check() { if [ "$2" = "1" ]; then ok "$1"; else bad "$1${3:+  ($3)}"; fi; }
note()  { echo "  · $1"; }
json()  { python3 -c "import sys, json; d = json.load(sys.stdin); $1" 2>/dev/null; }
token() { curl -s -X POST "$API/api/auth/token" -H 'content-type: application/json' -d "{\"user\":\"$1\",\"password\":\"$1\"}" | json 'print(d["access_token"])'; }
get()   { curl -s -H "Authorization: Bearer $1" "$API$2"; }
code()  { curl -s -o /dev/null -w "%{http_code}" -X "${3:-GET}" -H "Authorization: Bearer $1" "$API$2"; }
say() {  # token, text, thread
  local body
  body=$(python3 -c 'import json, sys; print(json.dumps({"message": sys.argv[1], "thread_id": sys.argv[2]}))' "$2" "$3")
  curl -s -X POST "$API/api/chat" -H "Authorization: Bearer $1" -H 'content-type: application/json' -d "$body"
}

TS=$(date +%s)
MARK="validacion $TS"
T1="val-$TS-uno"
T2="val-$TS-dos"

echo "1. The API"
status=$(curl -s -o /dev/null -w "%{http_code}" "$API/health")
check "the API answers on $API" "$([ "$status" = 200 ] && echo 1 || echo 0)" "HTTP $status: start it with  make dev  or  make up"
[ "$status" = 200 ] || { echo; echo "Nothing else can be checked without the API."; exit 1; }

ready=$(curl -s "$API/health/ready")
llm=$(echo "$ready" | json 'print(d.get("llm", "?"))')
case "$llm" in
  ok*) ok "the model answers  ($llm)" ;;
  *)
    bad "the model is NOT available: $llm"
    echo
    echo "The agent cannot answer, so the memory cannot be validated. Fix the model first:"
    echo "  - Gemini: CLOUDSDK_CONFIG, GOOGLE_CLOUD_LOCATION and LLM_PROVIDER=google_genai in the terminal of 'make dev'"
    echo "  - Ollama: it must be running with the models downloaded"
    echo "  then:  curl -s $API/health/ready"
    exit 1
    ;;
esac

TA=$(token "$A"); TB=$(token "$B")
check "$A signs in" "$([ -n "$TA" ] && echo 1 || echo 0)"
check "$B signs in" "$([ -n "$TB" ] && echo 1 || echo 0)"
[ -n "$TA" ] && [ -n "$TB" ] || { echo; echo "Both demo customers must exist in the database."; exit 1; }

echo "2. The memory is on"
listed=$(code "$TA" /api/me/conversations)
if [ "$listed" = 404 ]; then
  bad "the memory is OFF in this API  (put CHAT_MEMORY_ENABLED=true in .env and restart it; with Docker, make up)"
  echo; echo "$pass passed, $fail failed"; exit 1
fi
check "the history route answers 200" "$([ "$listed" = 200 ] && echo 1 || echo 0)" "HTTP $listed: has migration 003 and 004 been applied to the database?"

echo "2b. A clean slate"
hidA=$(curl -s -X DELETE -H "Authorization: Bearer $TA" "$API/api/me/conversations" | json 'print(d.get("hidden", "?"))')
hidB=$(curl -s -X DELETE -H "Authorization: Bearer $TB" "$API/api/me/conversations" | json 'print(d.get("hidden", "?"))')
check "the earlier conversations of A and B are out of sight (they stay in the database)" "$([ -n "$hidA" ] && [ -n "$hidB" ] && echo 1 || echo 0)"
note "hid $hidA of A and $hidB of B from earlier runs; this run starts with nothing to remember"
[ "$(get "$TA" /api/me/conversations | json 'print(len(d))')" = 0 ] && ok "A's history is empty before it starts" || bad "A's history is not empty before it starts"

echo "3. Customer A writes two messages in one chat"
r1=$(say "$TA" "$MARK: ¿cuál es mi saldo?" "$T1")
reply1=$(echo "$r1" | json 'print(d.get("reply") or "")')
broke=$(echo "$r1" | json 'h = d.get("handoff") or {}; print(1 if h.get("reason") == "assistant_error" else 0)')
if [ "$broke" = 1 ]; then
  bad "the agent FAILED on the first message and answered with its emergency text:"
  echo "      $(echo "$reply1" | tr '\n' ' ' | head -c 200)"
  echo
  echo "The model or a tool broke. The terminal of the API shows 'agent turn failed' and the cause."
  echo "If that cause says PERMISSION_DENIED (403) on aiplatform: the API was started WITHOUT the Google account."
  echo "Stop it (Ctrl+C) and, in that same terminal and BEFORE  make dev :"
  echo "    export CLOUDSDK_CONFIG=\$HOME/.config/gcloud-factored"
  echo "If  make dev  says 'Address already in use', an old API is still answering: lsof -ti :8080 | xargs kill"
  echo "The chat is now with a person, so the next messages of that thread get no answer: that is how the agent"
  echo "behaves, and it is why nothing more can be validated now. Fix it, then run this script again."
  echo "$pass passed before it, $fail failed."
  exit 1
fi
check "the agent answers the first message" "$([ -n "$reply1" ] && echo 1 || echo 0)" "$(echo "$r1" | head -c 160)"
r2=$(say "$TA" "gracias" "$T1")
check "and the second" "$([ -n "$(echo "$r2" | json 'print(d.get("reply") or "")')" ] && echo 1 || echo 0)"
sleep 2   # the turn is kept after the answer, in the background

echo "4. It is kept, per customer, and can be read"
list=$(get "$TA" /api/me/conversations)
ID1=$(echo "$list" | json "print(next((c['conversation_id'] for c in d if (c['title'] or '').startswith('$MARK')), ''))")
check "the conversation is in A's list" "$([ -n "$ID1" ] && echo 1 || echo 0)"
if [ -n "$ID1" ]; then
  msgs=$(echo "$list" | json "print(next(c['messages'] for c in d if c['conversation_id'] == '$ID1'))")
  check "with its 4 messages (2 of A, 2 of the agent)" "$([ "$msgs" = 4 ] && echo 1 || echo 0)" "has $msgs"
  one=$(get "$TA" "/api/me/conversations/$ID1")
  roles=$(echo "$one" | json "print(','.join(m['role'] for m in d['messages']))")
  check "opened, it reads customer, assistant, customer, assistant" "$([ "$roles" = "customer,assistant,customer,assistant" ] && echo 1 || echo 0)" "$roles"
  first=$(echo "$one" | json "print(d['messages'][0]['content'])")
  check "and the first message is what A wrote" "$([ "$first" = "$MARK: ¿cuál es mi saldo?" ] && echo 1 || echo 0)"
fi

echo "5. Customer B sees nothing of it"
check "B's list has none of A's conversations" "$([ "$(get "$TB" /api/me/conversations | json "print(sum((c['title'] or '').startswith('$MARK') for c in d))")" = 0 ] && echo 1 || echo 0)"
if [ -n "$ID1" ]; then
  check "B cannot open A's conversation by its id (404)" "$([ "$(code "$TB" "/api/me/conversations/$ID1")" = 404 ] && echo 1 || echo 0)"
fi
notoken=$(curl -s -w ' HTTP %{http_code}' "$API/api/me/conversations")
closed=1
case "$notoken" in *"HTTP 200") closed=0 ;; esac
check "without a token the history is closed (it hands over no conversations)" "$closed" "answered: $notoken"

echo "6. A new chat: does the agent remember?"
# No marker in this question: the marker of this run is in the FIRST chat, and the answer can only have it by remembering.
r3=$(say "$TA" "validacion-pregunta: ¿qué fue lo primero que te pregunté en mi conversación anterior? Cítalo tal cual." "$T2")
reply3=$(echo "$r3" | json 'print(d.get("reply") or "")')
check "the agent answers" "$([ -n "$reply3" ] && echo 1 || echo 0)"
note "the agent said: $(echo "$reply3" | tr '\n' ' ' | head -c 300)"
# A real memory quotes what was asked in the first chat: the marker of this run (only that chat has it) or the
# question itself. The word "saldo" alone is NOT proof (the generic greeting says "consultas sobre tus saldos"),
# and neither is a paraphrase we cannot verify: if the agent worded it another way, read the sentence above.
lower=$(echo "$reply3" | tr '[:upper:]' '[:lower:]')
remembers=0
case "$lower" in
  *"validacion $TS"*|*"cuál es mi saldo"*|*"cual es mi saldo"*|*"qual é o meu saldo"*) remembers=1 ;;
esac
check "the agent remembers: its answer quotes what A asked before" "$remembers" "it did not. Read the sentence above"
if [ "$remembers" = 0 ]; then
  echo "      Look at the terminal of the API, at the line 'chat memory: N earlier conversation(s) told to the agent':"
  echo "        - N is 0 or the line is missing  -> the history never reached the agent (a wiring problem)"
  echo "        - N is 1 or more                 -> the agent had it and did not use it (a prompt problem)"
fi
sleep 2

echo "7. Hiding takes it out of sight, but nothing is deleted"
hidden=$(curl -s -X DELETE -H "Authorization: Bearer $TA" "$API/api/me/conversations?thread_id=$T2" | json 'print(d.get("hidden", "?"))')
check "A hides the earlier conversations, keeping the chat in use" "$([ "$hidden" -ge 1 ] 2>/dev/null && echo 1 || echo 0)" "answered: $hidden"
after=$(get "$TA" /api/me/conversations)
check "A no longer sees the first conversation" "$([ "$(echo "$after" | json "print(sum(c['conversation_id'] == '$ID1' for c in d))")" = 0 ] && echo 1 || echo 0)"
check "but still sees the chat in use (the second one)" "$([ "$(echo "$after" | json "print(sum((c['title'] or '').startswith('validacion-pregunta') for c in d))")" -ge 1 ] 2>/dev/null && echo 1 || echo 0)"
if [ -n "$ID1" ]; then
  check "the hidden one can no longer be opened (404)" "$([ "$(code "$TA" "/api/me/conversations/$ID1")" = 404 ] && echo 1 || echo 0)"
fi

echo "8. The database still has it"
if command -v psql >/dev/null 2>&1; then
  row=$(psql "$DB" -Atc "SELECT count(*) || ',' || count(hidden_at) || ',' || (SELECT count(*) FROM ops.messages WHERE conversation_id = '${ID1:-00000000-0000-0000-0000-000000000000}') FROM ops.conversations WHERE title LIKE '$MARK%'" 2>&1)
  conversations=${row%%,*}
  check "the first conversation of this run is still in ops.conversations" "$([ "${conversations:-0}" -ge 1 ] 2>/dev/null && echo 1 || echo 0)" "psql said: $row"
  hidden_rows=$(echo "$row" | cut -d, -f2)
  check "the first one is marked hidden, not removed" "$([ "${hidden_rows:-0}" -ge 1 ] 2>/dev/null && echo 1 || echo 0)"
  kept_messages=$(echo "$row" | cut -d, -f3)
  check "and its $msgs messages are all still in ops.messages" "$([ "${kept_messages:-x}" = "${msgs:-y}" ] && echo 1 || echo 0)" "the database has ${kept_messages:-?}"
  echo "  see it yourself:  psql $DB -c \"SELECT customer_id, title, hidden_at FROM ops.conversations WHERE title LIKE '$MARK%'\""
else
  note "psql is not installed: skipped. Check it by hand with  SELECT customer_id, title, hidden_at FROM ops.conversations ORDER BY last_message_at DESC LIMIT 5;"
fi

echo
echo "$pass passed, $fail failed."
echo "These conversations stay in the demo database (A's are hidden). To remove them for good:"
echo "  psql $DB -c \"DELETE FROM ops.messages WHERE conversation_id IN (SELECT conversation_id FROM ops.conversations WHERE title LIKE 'validacion%'); DELETE FROM ops.conversations WHERE title LIKE 'validacion%';\""
[ "$fail" = 0 ]
