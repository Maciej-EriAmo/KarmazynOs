# Stage 2 smoke — save/load + root bind + assert (no Python)
#   karmazyn_shell examples/smoke.ksh
# Paths relative to cwd; stage2_verify uses out/.

atom var hello 50
bubble root
root 0
bind 0 hi 0
setval 0 99
assert has 0
assert lookup 0 hi 0
assert nodead 0
assert t 0 gt 0
list
stats
save out/shell_smoke.ksub
load out/shell_smoke.ksub
lookup 0 hi
assert lookup 0 hi 0
val 0
stats
echo smoke_ok
quit
