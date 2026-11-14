#!/bin/bash
# Called by FPP's Plugin Manager on uninstall. Counts are kept on purpose.
"$(cd "$(dirname "$0")" && pwd)/service.sh" stop
echo "Car Counter stopped. Your counts remain in /home/fpp/media/config/fpp-car-counter/ - delete that folder to remove them."
exit 0
