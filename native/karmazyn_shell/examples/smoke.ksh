# Stage 2 smoke — save/load + root bind (no Python)
#   karmazyn_shell examples/smoke.ksh
# Paths relative to cwd; stage2_verify uses out/.

atom var hello 50
bubble root
root 0
bind 0 hi 0
stats
save out/shell_smoke.ksub
# wipe-ish: load restores
load out/shell_smoke.ksub
lookup 0 hi
stats
quit
