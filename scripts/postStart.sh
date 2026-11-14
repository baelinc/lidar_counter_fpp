#!/bin/bash
# Called by FPP when fppd starts: make sure the counter daemon is running.
exec "$(dirname "$0")/service.sh" start
