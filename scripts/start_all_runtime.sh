#!/bin/bash

PID_SERVER=""
PID_NODE=""
PID_BOT=""

declare -A RESTART_COUNT
declare -A RESTART_SINCE

cleanup() {
    echo -e "\n${YELLOW}Shutting down all apps...${NC}"
    kill $PID_SERVER $PID_NODE $PID_BOT 2>/dev/null
    wait $PID_SERVER $PID_NODE $PID_BOT 2>/dev/null
    echo -e "${GREEN}All stopped.${NC}"
    exit 0
}

restart_app() {
    local name="$1"
    local pid_var="$2"
    shift 2
    local cmd=("$@")
    local old_pid="${!pid_var}"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        kill "$old_pid" 2>/dev/null
        wait "$old_pid" 2>/dev/null
    fi
    echo -e "${CYAN}[$(date +%H:%M:%S)] Starting $name...${NC}"
    "${cmd[@]}" &
    local new_pid=$!
    eval "$pid_var=$new_pid"
    echo -e "${GREEN}[$(date +%H:%M:%S)] $name started (PID: $new_pid)${NC}"
}

monitor_and_restart() {
    local name="$1"
    local pid_var="$2"
    shift 2
    local cmd=("$@")
    local pid="${!pid_var}"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && return
    local now=$(date +%s)
    local key="$name"
    local since="${RESTART_SINCE[$key]:-0}"
    local count="${RESTART_COUNT[$key]:-0}"
    if [ $((now - since)) -gt $RAPID_WINDOW ]; then
        count=0
    fi
    if [ "$count" -ge "$MAX_RAPID_RESTARTS" ]; then
        echo -e "${RED}[$(date +%H:%M:%S)] $name crashed $count times in ${RAPID_WINDOW}s; pausing 30s...${NC}"
        sleep 30
        count=0
    fi
    echo -e "${YELLOW}[$(date +%H:%M:%S)] $name died; restarting in ${RETRY_DELAY}s (attempt $((count+1)))...${NC}"
    sleep "$RETRY_DELAY"
    restart_app "$name" "$pid_var" "${cmd[@]}"
    RESTART_COUNT[$key]=$((count + 1))
    RESTART_SINCE[$key]=$(date +%s)
}

