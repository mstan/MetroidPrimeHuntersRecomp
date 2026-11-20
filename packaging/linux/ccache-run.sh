#!/bin/sh
# Run a build command with per-run ccache statistics: zero the counters, run,
# then print them. Installed in the build image as /usr/local/bin/mph-ccache-run.
ccache -z >/dev/null
"$@"
rc=$?
echo "== ccache statistics (this run) =="
ccache -s
exit $rc
