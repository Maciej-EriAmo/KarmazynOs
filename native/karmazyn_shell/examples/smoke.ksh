# Stage 2 smoke — save/load + root bind + assert (no Python)
#   karmazyn_shell examples/smoke.ksh
# Paths relative to cwd; stage2_verify uses out/.
# @root = id bąbla "root" (shell zakłada też własne bąble repl/lua).

atom var hello 50
bubble root
root @root
bind @root hi 0
setval 0 99
assert has 0
assert lookup @root hi 0
assert nodead 0
assert t 0 gt 0
list
bubbles
roots
binds @root
info 0
assert val 0 99
assert stats total eq 1
assert root @root
stats
save out/shell_smoke.ksub
load out/shell_smoke.ksub
lookup @root hi
assert lookup @root hi 0
val 0
stats
echo smoke_ok
quit
